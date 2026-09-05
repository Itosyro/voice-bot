"""Chromium smoke tests with mocked /api/state; never connect to a real DVIZH server.

Run: pip install playwright==1.57.0; playwright install chromium
     python tests/ai-home-v2/browser_test.py
Uses system chromium when present. No real microphone/Hermes claim is made.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'test-results'
IN_MEMORY = os.environ.get('DVIZH_BROWSER_IN_MEMORY') == '1'
MANUAL = b'<!doctype html><html lang="ru"><title>Manual fixture</title><body><main id="manual">STABLE MANUAL</main><script src="/app.js"></script></body></html>'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.split('?')[0]
        static = {
            '/': (MANUAL, 'text/html'),
            '/manual.html': (MANUAL, 'text/html'),
            '/app.js': (b'window.manualReady = true;', 'text/javascript'),
            '/sw.js': (b"self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));", 'text/javascript'),
            '/favicon.ico': (b'', 'image/x-icon'),
        }
        for route, filename, mime in [('/ai-home-v2-preview.html', 'index.html', 'text/html'), ('/ai-home-v2.js', 'ai-home-v2.js', 'text/javascript'), ('/ai-home-v2.css', 'ai-home-v2.css', 'text/css')]:
            static[route] = ((ROOT / 'ai-home-v2' / filename).read_bytes(), mime)
        if name not in static:
            self.send_error(404)
            return
        data, mime = static[name]
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass

class BrowserSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RESULTS.mkdir(exist_ok=True)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        executable = os.environ.get('CHROMIUM_EXECUTABLE') or shutil.which('chromium')
        cls.browser = cls.pw.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.revision = 1
        self.state = {'tasks': [{'id': 'fixture-task', 'title': 'Keep me'}], 'aiProposals': [{'id': 'fixture-proposal', 'status': 'pending'}]}
        self.gets = self.puts = 0
        self.deny = False
        self.context.route('**/api/state', self.api)
        self.init_scripts = []
        if IN_MEMORY:
            self.page.expose_binding('__fixtureApi', lambda _source, method, body: self.api_result(method, json.loads(body) if body else None))

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def api_result(self, method, body):
        if self.deny:
            return {'status': 401, 'payload': {'error': 'auth'}}
        if method == 'PUT':
            self.puts += 1
            if body['baseRevision'] != self.revision:
                return {'status': 409, 'payload': {'error': 'conflict'}}
            self.state = body['state']
            self.revision += 1
            return {'status': 200, 'payload': {'ok': True, 'revision': self.revision}}
        self.gets += 1
        return {'status': 200, 'payload': {'revision': self.revision, 'state': self.state}}

    def api(self, route):
        result = self.api_result(route.request.method, route.request.post_data_json)
        route.fulfill(status=result['status'], json=result['payload'])

    def load(self):
        if IN_MEMORY:
            # Rendering-only fallback when the host browser prohibits navigation.
            # No network policy is changed; all fixtures stay in memory.
            html = (ROOT / 'ai-home-v2/index.html').read_text()
            html = html.replace('<link rel="stylesheet" href="/ai-home-v2.css?v=20260905-3.1">', '')
            html = html.replace('<script src="/ai-home-v2.js?v=20260905-3.1" defer></script>', '')
            self.page.set_content(html)
            self.page.add_style_tag(path=str(ROOT / 'ai-home-v2/ai-home-v2.css'))
            self.page.evaluate("""() => { window.fetch = async (_url, options = {}) => {
              const result = await window.__fixtureApi(options.method, options.body || null);
              return new Response(JSON.stringify(result.payload), {status: result.status});
            }; };""")
            for script in self.init_scripts:
                self.page.add_script_tag(content=script)
            self.page.add_script_tag(path=str(ROOT / 'ai-home-v2/ai-home-v2.js'))
        else:
            for script in self.init_scripts:
                self.page.add_init_script(script)
            self.page.goto(self.origin + '/ai-home-v2-preview.html')

    def open(self):
        self.load()
        expect(self.page.locator('#aiInput')).to_be_enabled()

    def finish(self, content='Готово. Ничего не изменено без подтверждения.'):
        self.page.wait_for_function("document.getElementById('aiInput').value === ''")
        for request in self.state.get('aiHomeRequests', []):
            request['status'] = 'done'
        self.state['aiHomeMessages'] = [{'role': 'assistant', 'content': content}]
        self.state['aiHomeStatus'] = {'state': 'ready'}
        self.revision += 1
        expect(self.page.locator('#aiAnswer')).to_have_text(content, timeout=6000)

    def test_01_minimal_idle_has_no_old_bundle_or_idle_poll(self):
        self.open()
        self.assertEqual(self.page.locator('body').evaluate("el => getComputedStyle(el).backgroundColor"), 'rgb(0, 0, 0)')
        expect(self.page.locator('#aiAnswer')).to_be_hidden()
        expect(self.page.locator('#aiStatus')).to_have_text('')
        self.assertEqual(self.page.locator('nav, .card, .check-in').count(), 0)
        self.assertEqual(self.page.locator('script[src*="app.js"]').count(), 0)
        self.assertFalse(self.page.evaluate('Boolean(window.manualReady)'))
        before = self.gets
        self.page.wait_for_timeout(1300)
        self.assertEqual(self.gets, before)
        self.page.screenshot(path=str(RESULTS / 'preview-idle-390x844.png'))

    def test_02_double_submit_answer_and_data_preservation(self):
        self.open()
        self.page.locator('#aiInput').fill('Как спланировать день?')
        self.page.evaluate("() => { const form = document.getElementById('aiComposer'); form.requestSubmit(); form.requestSubmit(); }")
        expect(self.page.locator('#aiStatus')).to_have_text('Думаю…')
        self.finish()
        self.assertEqual(self.puts, 1)
        self.assertEqual(self.state['tasks'], [{'id': 'fixture-task', 'title': 'Keep me'}])
        self.assertEqual(self.state['aiProposals'][0]['status'], 'pending')
        expect(self.page.locator('#aiInput')).to_have_value('')

    def test_03_mobile_viewports_keep_input_and_send_on_screen(self):
        self.open()
        for width, height in [(320, 568), (390, 844), (390, 380), (844, 390), (1440, 900)]:
            self.page.set_viewport_size({'width': width, 'height': height})
            self.page.wait_for_function('Math.abs(parseFloat(getComputedStyle(document.getElementById("aiApp")).height) - window.visualViewport.height) < 2')
            for selector in ['#aiInput', '#aiSend', '#aiOrb']:
                box = self.page.locator(selector).bounding_box()
                self.assertIsNotNone(box)
                self.assertGreaterEqual(box['y'], 0)
                self.assertLessEqual(box['y'] + box['height'], height + 1)
                self.assertGreaterEqual(box['x'], 0)
                self.assertLessEqual(box['x'] + box['width'], width + 1)
        self.page.screenshot(path=str(RESULTS / 'preview-idle-desktop.png'))

    def test_04_stale_saved_answer_is_hidden_until_this_page_observes_a_request(self):
        old = '<b>Это старый текст, не HTML</b>\n' + '\n'.join(f'Старая строка {i}.' for i in range(20))
        self.state['aiHomeRequests'] = [{'id': 'old', 'text': 'Вчера', 'status': 'done'}]
        self.state['aiHomeMessages'] = [{'role': 'assistant', 'content': old}]
        self.state['aiHomeStatus'] = {'state': 'ready', 'requestId': 'old', 'updatedAt': '2026-09-05T13:46:13Z'}
        self.open()
        expect(self.page.locator('#aiAnswer')).to_be_hidden()
        expect(self.page.locator('#aiStatus')).to_have_text('')

        content = '<b>Это новый текст, не HTML</b>\n' + '\n'.join(f'Строка {i}: продолжение ответа.' for i in range(80))
        self.page.locator('#aiInput').fill('Новый запрос')
        self.page.locator('#aiInput').press('Enter')
        expect(self.page.locator('#aiStatus')).to_have_text('Думаю…')
        self.finish(content)

        self.page.set_viewport_size({'width': 390, 'height': 380})
        expect(self.page.locator('#aiAnswer')).to_be_visible()
        self.assertEqual(self.page.locator('#aiAnswer b').count(), 0)
        self.assertTrue(self.page.locator('#aiAnswer').evaluate('el => el.scrollHeight > el.clientHeight'))
        self.page.locator('#aiAnswer').evaluate('el => el.scrollTop = 100')
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.page.wait_for_timeout(200)
        self.assertGreater(self.page.locator('#aiAnswer').evaluate('el => el.scrollTop'), 0)
        self.page.screenshot(path=str(RESULTS / 'preview-answer-390x380.png'))

    @unittest.skipIf(IN_MEMORY, 'requires a real origin; requires normal CI mode')
    def test_05_manual_and_back_navigation_remain_usable(self):
        self.open()
        for _ in range(3):
            self.page.locator('#aiInput').fill('/manual')
            self.page.locator('#aiInput').press('Enter')
            expect(self.page.locator('#manual')).to_have_text('STABLE MANUAL')
            self.assertTrue(self.page.evaluate('window.manualReady'))
            self.page.go_back()
            expect(self.page.locator('#aiInput')).to_be_enabled()
        self.page.locator('#aiInput').fill('После возвращения')
        self.page.locator('#aiInput').press('Enter')
        expect(self.page.locator('#aiStatus')).to_have_text('Думаю…')
        self.finish()
        self.assertEqual(self.puts, 1)

    def test_06_auth_overlay_really_hides_composer(self):
        self.deny = True
        self.load()
        expect(self.page.locator('#aiAuth')).to_be_visible()
        expect(self.page.locator('#aiComposer')).to_be_hidden()
        self.assertEqual(self.puts, 0)

    def test_07_microphone_denial_does_not_submit_existing_text(self):
        self.init_scripts.append("""window.SpeechRecognition = class {
          start() { const end = this.onend; this.onstart?.(); queueMicrotask(() => { this.onerror?.({error:'not-allowed'}); end?.(); }); }
          abort() {} stop() {}
        };""")
        self.open()
        self.page.locator('#aiInput').fill('Не отправлять этот черновик')
        self.page.locator('#aiOrb').click()
        expect(self.page.locator('#aiStatus')).to_have_text('Нет доступа к микрофону. Можно написать.')
        expect(self.page.locator('#aiInput')).to_have_value('Не отправлять этот черновик')
        self.assertEqual(self.puts, 0)

    @unittest.skipIf(IN_MEMORY, 'requires a real origin; requires normal CI mode')
    def test_08_existing_service_worker_and_named_cache_survive_preview(self):
        self.page.goto(self.origin + '/manual.html')
        self.page.evaluate("""async () => {
          await navigator.serviceWorker.register('/sw.js');
          await navigator.serviceWorker.ready;
          const cache = await caches.open('manual-fixture-cache');
          await cache.put('/keep', new Response('KEEP'));
        }""")
        self.open()
        self.assertEqual(self.page.evaluate('(async () => (await navigator.serviceWorker.getRegistrations()).length)()'), 1)
        self.assertEqual(self.page.evaluate("(async () => (await (await caches.open('manual-fixture-cache')).match('/keep')).text())()"), 'KEEP')

    def test_09_reduced_motion_disables_orb_animation(self):
        self.page.emulate_media(reduced_motion='reduce')
        self.open()
        self.assertEqual(self.page.locator('#aiOrb span').first.evaluate('el => getComputedStyle(el).animationName'), 'none')

if __name__ == '__main__':
    unittest.main(verbosity=2)
