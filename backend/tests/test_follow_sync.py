import time

import httpx
from fastapi.testclient import TestClient

from backend.app.live import BilibiliReader
from backend.app.main import create_app

HEADERS = {"X-UPDesk-Local": "1"}


def wait_status(client, expected, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.post('/api/live/sync-status', headers=HEADERS).json()
        if status['state'] in expected:
            return status
        time.sleep(.01)
    raise AssertionError(status)


def build(tmp_path, mode='normal', logged_in=True):
    calls = []
    state = {'ids': ['2', '3', '4'], 'mode': mode}

    def respond(request):
        path = request.url.path
        calls.append((path, dict(request.url.params)))
        if path.endswith('/qrcode/poll'):
            return httpx.Response(200, json={'code': 0, 'data': {'code': 0, 'url': 'https://passport.bilibili.com/?SESSDATA=fake'}})
        if path == '/x/web-interface/nav':
            return httpx.Response(200, json={'code': 0, 'data': {'isLogin': True, 'mid': 1, 'uname': 'owner'}})
        if path == '/x/relation/tags':
            return httpx.Response(200, json={'code': 0, 'data': []})
        assert path == '/x/relation/followings', 'Sync must not fetch content'
        pn, ps = int(request.url.params['pn']), int(request.url.params['ps'])
        if state['mode'] == 'risk':
            return httpx.Response(412)
        if state['mode'] == 'expired':
            return httpx.Response(200, json={'code': -101})
        ids = state['ids'][(pn - 1) * ps:pn * ps]
        total = len(state['ids'])
        if pn == 2 and state['mode'] == 'empty':
            ids = []
        if pn == 2 and state['mode'] == 'repeat':
            ids = state['ids'][:ps]
        if pn == 2 and state['mode'] == 'changed':
            total += 1
        return httpx.Response(200, json={'code': 0, 'data': {'total': total, 'list': [{'mid': uid, 'uname': uid} for uid in ids]}})

    reader = BilibiliReader(transport=httpx.MockTransport(respond), interval=.01)
    if logged_in:
        reader.account = {'uid': '1', 'name': 'owner'}
        reader.cookie = 'SESSDATA=fake'
    app = create_app(tmp_path / 'demo.db', tmp_path / 'dist', reader)
    reader.sync.page_size = 2
    return TestClient(app), reader, calls, state


def test_login_starts_full_sync_and_cache_cannot_reset_job(tmp_path):
    client, reader, calls, state = build(tmp_path, logged_in=False)
    with client:
        reader.key = 'fake'
        reader.qr_started = time.monotonic()
        assert client.post('/api/live/poll', headers=HEADERS).json()['state'] == 'connected'
        client.post('/api/live/cache', headers=HEADERS)
        result = wait_status(client, {'complete'})
        assert (result['loaded'], result['total'], result['added']) == (3, 3, 3)
        assert result['next_run'] and result['last_success']
        assert [params['pn'] for path, params in calls if path == '/x/relation/followings'] == ['1', '2']
        assert len(reader.repository.load('1')['items']) == 3


def test_periodic_sync_discovers_new_following_without_monitoring(tmp_path):
    client, reader, calls, state = build(tmp_path)
    reader.sync.refresh_seconds = .15
    with client:
        client.post('/api/live/sync-start', headers=HEADERS)
        first = wait_status(client, {'complete'})
        state['ids'].append('5')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = client.post('/api/live/sync-status', headers=HEADERS).json()
            if result['state'] == 'complete' and result['last_success'] != first['last_success']:
                break
            time.sleep(.02)
        assert result['total'] == 4 and result['added'] == 1
        assert len(reader.repository.load('1')['items']) == 4


def test_duplicate_start_stop_and_restart_status(tmp_path):
    client, reader, calls, state = build(tmp_path)
    state['ids'] = [str(i) for i in range(2, 102)]
    reader.interval = .08
    with client:
        client.post('/api/live/sync-start', headers=HEADERS)
        task = reader.sync.task
        client.post('/api/live/sync-start', headers=HEADERS)
        assert task is reader.sync.task
        assert client.post('/api/live/followings', headers=HEADERS).status_code == 409
        client.post('/api/live/sync-stop', headers=HEADERS)
        assert wait_status(client, {'stopped'})['next_run'] is None
        count = len(calls)
        time.sleep(.1)
        assert len(calls) == count
    client, reader, _, _ = build(tmp_path)
    with client:
        assert client.post('/api/live/sync-status', headers=HEADERS).json()['state'] == 'stopped'
        client.post('/api/live/disconnect', headers=HEADERS)
        assert client.post('/api/live/sync-status', headers=HEADERS).json()['account_uid'] is None


def test_failures_stop_without_retry(tmp_path):
    for mode in ('risk', 'repeat', 'empty', 'changed'):
        client, reader, calls, state = build(tmp_path / mode, mode=mode)
        reader.sync.refresh_seconds = .02
        with client:
            client.post('/api/live/sync-start', headers=HEADERS)
            status = wait_status(client, {'error', 'incomplete'})
            assert status['last_success'] is None and status['next_run'] is None
            count = len(calls)
            time.sleep(.06)
            assert len(calls) == count


def test_expired_login_stops_and_hides_previous_status(tmp_path):
    client, reader, calls, _ = build(tmp_path, mode='expired')
    with client:
        client.post('/api/live/sync-start', headers=HEADERS)
        deadline = time.monotonic() + 2
        while reader.account is not None and time.monotonic() < deadline:
            time.sleep(.01)
        assert reader.account is None
        assert client.post('/api/live/sync-status', headers=HEADERS).json()['account_uid'] is None
        assert reader.repository.load_sync('1')['state'] == 'error'
        assert len(calls) == 1


def test_cache_during_sweep_and_disconnect_cancel(tmp_path):
    client, reader, calls, state = build(tmp_path)
    state['ids'] = [str(i) for i in range(2, 102)]
    reader.interval = .03
    with client:
        client.post('/api/live/sync-start', headers=HEADERS)
        assert reader.sync.running
        client.post('/api/live/cache', headers=HEADERS)
        status = client.post('/api/live/sync-status', headers=HEADERS).json()
        assert status['state'] == 'running' and status['page'] >= 1
        client.post('/api/live/disconnect', headers=HEADERS)
        count = len(calls)
        time.sleep(.08)
        assert len(calls) == count
        assert reader.repository.load_sync('1')['state'] == 'stopped'
        pages = [int(params['pn']) for path, params in calls if path == '/x/relation/followings']
        assert pages == list(range(1, len(pages) + 1))


def test_interrupted_status_not_complete_after_restart(tmp_path):
    client, reader, _, _ = build(tmp_path)
    with client:
        reader.repository.save_sync('1', {'state': 'running', 'account_uid': '1', 'page': 2, 'loaded': 4,
            'total': 10, 'added': 4, 'last_success': None, 'next_run': 'stale', 'error': ''})
    client, reader, _, _ = build(tmp_path)
    with client:
        status = client.post('/api/live/sync-status', headers=HEADERS).json()
        assert status['state'] == 'stopped' and status['next_run'] is None
        reader.account = {'uid': 'other', 'name': 'other'}
        assert client.post('/api/live/sync-status', headers=HEADERS).json()['state'] == 'idle'


def test_status_and_local_reads_not_blocked_between_pages(tmp_path):
    import asyncio
    from backend.app.follow_sync import FollowingSync

    class Probe:
        account = {'uid': '1'}
        cookie = 'SESSDATA=fake'
        interval = .08
        def __init__(self):
            self.lock = asyncio.Lock()
            self.allowed = set()
            self.repository = None
            self.groups_called = False
        def require_account(self):
            pass
        def local_operation(self, operation, *args):
            return {'items': []} if operation == 'load' else None
        async def following_page(self, page, size):
            await asyncio.sleep(.05)
            return {'items': [{'uid': str(page)}], 'total': 2}
        async def groups(self):
            self.groups_called = True

    async def check():
        probe = Probe()
        sync = FollowingSync(probe, refresh_seconds=1, page_size=1)
        sync.progress = {**sync.progress}
        task = asyncio.create_task(sync._sweep('1'))
        await asyncio.sleep(0)
        entered = time.monotonic()
        async with probe.lock:
            assert time.monotonic() - entered < .03
        await task
        assert probe.groups_called

    asyncio.run(check())
