"""Independent v2.2 review regressions; only temporary fixture paths are mutated."""
import concurrent.futures
import hashlib
import json
import multiprocessing
import os
import signal
import threading
import time
from pathlib import Path
from unittest.mock import patch

from test_release_v22 import TrustTests


class ReviewTests(TrustTests):
    def deploy(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        return self.g.apply(str(self.proposal_path), planned['approval_phrase'] if planned['risk'] == 'ai-integration-privileged' else planned['approval_token'])

    def assert_old(self):
        for row in self.rows:
            p = self.fs / row['target'].lstrip('/')
            self.assertEqual(p.read_bytes(), self.old)
            self.assertEqual(p.stat().st_mode & 0o7777, 0o755)

    def test_concurrent_claim_is_single_use_across_processes(self):
        challenge = self.g.create_approval(self.proposal, 'digest')
        ctx = multiprocessing.get_context('fork')
        start, results = ctx.Event(), ctx.Queue()
        compare = self.g.secrets.compare_digest
        def slow_compare(*args):
            time.sleep(0.2)
            return compare(*args)
        def claim():
            start.wait(3)
            try:
                with patch.object(self.g.secrets, 'compare_digest', side_effect=slow_compare):
                    self.g.consume_approval(self.proposal, 'digest', challenge['approval_token'])
                results.put('claimed')
            except self.g.GateError:
                results.put('denied')
        children = [ctx.Process(target=claim) for _ in range(2)]
        for child in children: child.start()
        start.set()
        for child in children:
            child.join(5)
            self.assertEqual(child.exitcode, 0)
        self.assertEqual(sorted(results.get(timeout=1) for _ in children), ['claimed', 'denied'])

    def test_plan_and_second_apply_wait_for_entire_transaction(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        entered, release, replanned, reapplied = (threading.Event() for _ in range(4))
        def health(plan):
            if not entered.is_set():
                entered.set()
                if not release.wait(5): raise RuntimeError('test timeout')
        def plan_again():
            result = self.g.plan_release(str(self.proposal_path))
            replanned.set()
            return result
        def apply_again():
            try: return self.g.apply(str(self.proposal_path), planned['approval_phrase'])
            except self.g.GateError: return None
            finally: reapplied.set()
        with patch.object(self.g, 'check_health', side_effect=health), concurrent.futures.ThreadPoolExecutor(3) as pool:
            first = pool.submit(self.g.apply, str(self.proposal_path), planned['approval_phrase'])
            self.assertTrue(entered.wait(3))
            second = pool.submit(plan_again)
            third = pool.submit(apply_again)
            try:
                self.assertFalse(replanned.wait(0.2), 'plan replaced challenge during active apply')
                self.assertFalse(reapplied.is_set(), 'second apply escaped transaction lock')
            finally: release.set()
            self.assertTrue(first.result()['ok'])
            second.result(); third.result()

    def test_keyboard_interrupt_rolls_back_all_files(self):
        original = self.g.atomic_write
        count = 0
        def interrupt(path, data, *args, **kwargs):
            nonlocal count
            if path.is_relative_to(self.fs):
                count += 1
                if count == 2: raise KeyboardInterrupt('injected termination')
            return original(path, data, *args, **kwargs)
        with patch.object(self.g, 'atomic_write', side_effect=interrupt), patch.object(self.g, 'http_get', return_value=b'healthy'):
            try:
                self.deploy()
            except BaseException as exc:
                self.assertIsInstance(exc, self.g.GateError)
                self.assertIn('rollback confirmed', str(exc))
            else:
                self.fail('termination did not fail the release')
        self.assert_old()

    def test_sigterm_rolls_back_and_sigkill_leaves_fail_closed_journal(self):
        self.publish()
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig):
                planned = self.g.plan_release(str(self.proposal_path))
                original = self.g.atomic_write
                def child():
                    count = 0
                    def terminate(path, data, *args, **kwargs):
                        nonlocal count
                        if path.is_relative_to(self.fs):
                            count += 1
                            if count == 2: os.kill(os.getpid(), sig)
                        return original(path, data, *args, **kwargs)
                    with patch.object(self.g, 'atomic_write', side_effect=terminate), patch.object(self.g, 'http_get', return_value=b'healthy'):
                        try: self.g.apply(str(self.proposal_path), planned['approval_phrase'])
                        except self.g.GateError: return
                process = multiprocessing.get_context('fork').Process(target=child)
                process.start(); process.join(5)
                self.assertFalse(process.is_alive())
                if sig == signal.SIGTERM:
                    self.assertEqual(process.exitcode, 0)
                    self.assert_old()
                else:
                    self.assertEqual(process.exitcode, -signal.SIGKILL)
                    with self.assertRaisesRegex(self.g.GateError, 'pending|interrupted'):
                        self.g.plan_release(str(self.proposal_path))
                    with self.assertRaisesRegex(self.g.GateError, 'pending|interrupted'):
                        self.g.apply(str(self.proposal_path), planned['approval_phrase'])

    def test_untrusted_privileged_ancestors_denied(self):
        self.publish()
        parent = self.fs / 'opt/dvizh-ai-approval'
        parent.chmod(0o775)
        with self.assertRaisesRegex(self.g.GateError, 'ancestor|parent'): self.load()

    def test_ancestor_rename_restores_pinned_object_and_never_confirms_canonical(self):
        parent = self.fs / 'usr/local/libexec'
        moved = parent.with_name('moved')
        replace = self.g.os.replace
        renamed = False
        def rename_before_replace(src, dst, *args, **kwargs):
            nonlocal renamed
            if dst == 'dvizh-context' and not renamed:
                renamed = True
                parent.rename(moved)
                parent.mkdir()
                for row in self.rows[:2]:
                    p = parent / Path(row['target']).name
                    p.write_bytes(self.old); p.chmod(0o755)
            return replace(src, dst, *args, **kwargs)
        with patch.object(self.g.os, 'replace', side_effect=rename_before_replace), patch.object(self.g, 'http_get', return_value=b'healthy'):
            with self.assertRaisesRegex(self.g.GateError, 'CRITICAL.*rollback unconfirmed'): self.deploy()
        self.assertEqual((moved / 'dvizh-context').read_bytes(), self.old)
        self.assert_old()
        with self.assertRaisesRegex(self.g.GateError, 'pending|interrupted'):
            self.g.plan_release(str(self.proposal_path))

    def test_return_outside_function_is_rejected_without_execution(self):
        self.new = b'return 42\n'
        for row in self.rows:
            (self.source / row['source']).write_bytes(self.new)
            row['sha256'] = hashlib.sha256(self.new).hexdigest()
        self.publish()
        with self.assertRaisesRegex(self.g.GateError, 'syntax'): self.load()

    def new_home(self):
        self.manifest = {'schema': 1, 'operations': [{'source': self.rows[0]['source'], 'target': '/opt/dvizh-ai-home/new/nested/helper.py'}], 'restarts': []}
        return self.fs / 'opt/dvizh-ai-home/new/nested/helper.py'

    def test_new_ai_home_parent_creation(self):
        target = self.new_home()
        with patch.object(self.g, 'http_get', return_value=b'healthy'):
            self.assertTrue(self.deploy()['ok'])
        self.assertEqual(target.read_bytes(), self.new)

    def test_absent_target_rollback_succeeds_before_first_write(self):
        target = self.new_home()
        original = self.g.atomic_write
        def fail(path, *args, **kwargs):
            if path == target: raise OSError('before creation')
            return original(path, *args, **kwargs)
        with patch.object(self.g, 'atomic_write', side_effect=fail):
            with self.assertRaisesRegex(self.g.GateError, 'rollback confirmed'): self.deploy()
        self.assertFalse(target.exists())

    def test_new_ai_home_symlink_parent_denied(self):
        self.new_home()
        outside = self.root / 'outside'; outside.mkdir()
        (self.fs / 'opt/dvizh-ai-home').symlink_to(outside, target_is_directory=True)
        with self.assertRaises((self.g.GateError, OSError)): self.deploy()
        self.assertEqual(list(outside.iterdir()), [])

    def test_post_health_file_drift_rolls_back(self):
        count = 0
        def health(plan):
            nonlocal count
            count += 1
            if count == 2:
                p = self.fs / self.rows[0]['target'].lstrip('/')
                p.write_bytes(b'# health changed bytes\n'); p.chmod(0o600)
        with patch.object(self.g, 'check_health', side_effect=health):
            with self.assertRaisesRegex(self.g.GateError, 'rollback confirmed'): self.deploy()
        self.assert_old()

    def test_post_rollback_health_metadata_drift_is_critical(self):
        count = 0
        def health(plan):
            nonlocal count
            count += 1
            if count == 2:
                (self.fs / self.rows[0]['target'].lstrip('/')).chmod(0o600)
        with patch.object(self.g, 'check_health', side_effect=health), patch.object(self.g, 'restart_service', side_effect=[self.g.GateError('restart failed'), None]):
            with self.assertRaisesRegex(self.g.GateError, 'CRITICAL.*rollback unconfirmed'): self.deploy()

    def test_new_ai_home_rollback_removes_created_file(self):
        target = self.new_home()
        count = 0
        def health(plan):
            nonlocal count
            count += 1
            if count == 2: raise self.g.GateError('post apply health failed')
        with patch.object(self.g, 'check_health', side_effect=health):
            with self.assertRaisesRegex(self.g.GateError, 'rollback confirmed'): self.deploy()
        self.assertFalse(target.exists())

    def test_pending_marker_even_corrupt_blocks_without_target_writes(self):
        self.publish()
        planned = self.g.plan_release(str(self.proposal_path))
        (self.g.APPROVAL_ROOT / 'pending.json').write_bytes(b'partial journal')
        with patch.object(self.g, 'atomic_write') as write:
            with self.assertRaisesRegex(self.g.GateError, 'pending'):
                self.g.apply(str(self.proposal_path), planned['approval_phrase'])
            write.assert_not_called()
        self.assert_old()

    def test_control_lock_symlink_and_writable_parent_denied(self):
        self.g.APPROVAL_ROOT.mkdir(mode=0o700)
        outside = self.root / 'outside'; outside.write_bytes(b'untouched')
        lock = self.g.APPROVAL_ROOT / 'transaction.lock'
        lock.symlink_to(outside)
        with self.assertRaises((self.g.GateError, OSError)):
            self.g.create_approval(self.proposal, 'digest')
        self.assertEqual(outside.read_bytes(), b'untouched')
        lock.unlink()
        self.g.APPROVAL_ROOT.chmod(0o777)
        with self.assertRaisesRegex(self.g.GateError, 'ancestor'):
            self.g.create_approval(self.proposal, 'digest')

    def test_compile_does_not_execute_candidate(self):
        sentinel = self.root / 'executed'
        self.new = f'open({str(sentinel)!r}, "w").write("executed")\n'.encode()
        for row in self.rows:
            (self.source / row['source']).write_bytes(self.new)
            row['sha256'] = hashlib.sha256(self.new).hexdigest()
        with patch.object(self.g, 'http_get', return_value=b'healthy'):
            self.assertTrue(self.deploy()['ok'])
        self.assertFalse(sentinel.exists())

    def test_rollback_post_restart_byte_drift_is_critical(self):
        count = 0
        def restart(service):
            nonlocal count
            count += 1
            if count == 1: raise self.g.GateError('initial restart failed')
            (self.fs / self.rows[0]['target'].lstrip('/')).write_bytes(b'# changed during rollback restart\n')
        with patch.object(self.g, 'restart_service', side_effect=restart), patch.object(self.g, 'http_get', return_value=b'healthy'):
            with self.assertRaisesRegex(self.g.GateError, 'CRITICAL.*rollback unconfirmed'): self.deploy()

    def test_identity_change_before_write_does_not_touch_moved_parent(self):
        parent = self.fs / 'usr/local/libexec'
        moved = parent.with_name('moved')
        original = self.g.atomic_write
        renamed = False
        def rename(path, data, *args, **kwargs):
            nonlocal renamed
            if path == parent / 'dvizh-context' and not renamed:
                renamed = True
                parent.rename(moved)
                parent.mkdir(mode=0o755)
                for row in self.rows[:2]:
                    p = parent / Path(row['target']).name
                    p.write_bytes(self.old); p.chmod(0o755)
            return original(path, data, *args, **kwargs)
        replace = self.g.os.replace
        def no_candidate_into_moved(src, dst, *args, **kwargs):
            if dst == 'dvizh-context':
                fd = kwargs['src_dir_fd']
                f = os.open(src, os.O_RDONLY, dir_fd=fd)
                try: self.assertEqual(os.read(f, 1024), self.old)
                finally: os.close(f)
            return replace(src, dst, *args, **kwargs)
        with patch.object(self.g, 'atomic_write', side_effect=rename), patch.object(self.g.os, 'replace', side_effect=no_candidate_into_moved), patch.object(self.g, 'http_get', return_value=b'healthy'):
            with self.assertRaisesRegex(self.g.GateError, 'CRITICAL.*rollback unconfirmed'): self.deploy()
        self.assertEqual((moved / 'dvizh-context').read_bytes(), self.old)

    def test_final_reserved_ids_and_separate_challenge_namespace(self):
        self.publish()
        for reserved in ('pending', 'transaction', 'transaction.lock', 'pending.json'):
            with self.subTest(reserved=reserved):
                proposal = dict(self.proposal, id=reserved)
                with self.assertRaisesRegex(self.g.GateError, 'reserved'):
                    self.g.create_approval(proposal, 'digest')
        self.assertFalse((self.g.APPROVAL_ROOT / 'pending.json').exists())
        planned = self.g.plan_release(str(self.proposal_path))
        self.assertEqual(self.g.approval_file(self.proposal['id']).parent,
                         self.g.APPROVAL_ROOT / 'challenges')
        self.g.consume_approval(self.proposal, planned['digest'], planned['approval_token'])

    def test_final_two_actual_sigterms_during_rollback_setup(self):
        self.publish()
        for broken_restore in (False, True):
            with self.subTest(broken_restore=broken_restore):
                planned = self.g.plan_release(str(self.proposal_path))
                ctx = multiprocessing.get_context('fork')
                results = ctx.Queue()
                def child():
                    original_write, original_signal = self.g.atomic_write, signal.signal
                    writes = 0
                    sent = []
                    def write(path, data, *args, **kwargs):
                        nonlocal writes
                        if path.is_relative_to(self.fs):
                            writes += 1
                            if writes == 2:
                                sent.append('first')
                                os.kill(os.getpid(), signal.SIGTERM)
                            if broken_restore and getattr(self.g._STATE, 'rolling_back', False):
                                raise OSError('restoration unavailable')
                        return original_write(path, data, *args, **kwargs)
                    def install(sig, handler):
                        if getattr(self.g._STATE, 'rolling_back', False) and len(sent) == 1:
                            sent.append('second')
                            os.kill(os.getpid(), signal.SIGTERM)
                        return original_signal(sig, handler)
                    with patch.object(self.g, 'atomic_write', side_effect=write), patch.object(signal, 'signal', side_effect=install), patch.object(self.g, 'http_get', return_value=b'healthy'):
                        try: self.g.apply(str(self.proposal_path), planned['approval_phrase'])
                        except BaseException as exc: results.put((type(exc).__name__, str(exc), sent))
                process = ctx.Process(target=child)
                process.start(); process.join(5)
                if process.is_alive():
                    process.kill(); process.join()
                    self.fail('signal regression timed out')
                self.assertEqual(process.exitcode, 0)
                kind, message, sent = results.get(timeout=1)
                self.assertEqual(sent, ['first', 'second'])
                self.assertEqual(kind, 'GateError')
                self.assertIn('CRITICAL: rollback unconfirmed' if broken_restore else 'rollback confirmed', message)
                if not broken_restore: self.assert_old()
                else:
                    with self.assertRaisesRegex(self.g.GateError, 'pending'):
                        self.g.plan_release(str(self.proposal_path))

    def test_final_journal_unlink_fsync_failure_is_critical_and_blocks(self):
        self.publish()
        for rollback in (False, True):
            with self.subTest(rollback=rollback):
                planned = self.g.plan_release(str(self.proposal_path))
                unlink, fsync = self.g.os.unlink, self.g.os.fsync
                armed = False
                injected = False
                def remove(path, *args, **kwargs):
                    nonlocal armed
                    result = unlink(path, *args, **kwargs)
                    if path == 'pending.json': armed = True
                    return result
                def sync(fd):
                    nonlocal injected
                    if armed and not injected:
                        injected = True
                        raise OSError('journal directory fsync failed')
                    return fsync(fd)
                with patch.object(self.g.os, 'unlink', side_effect=remove), patch.object(self.g.os, 'fsync', side_effect=sync), patch.object(self.g, 'http_get', return_value=b'healthy'), patch.object(self.g, 'restart_service', side_effect=[self.g.GateError('restart failed'), None] if rollback else None):
                    with self.assertRaisesRegex(self.g.GateError, 'CRITICAL'):
                        self.g.apply(str(self.proposal_path), planned['approval_phrase'])
                self.assertTrue(injected)
                marker = self.g.APPROVAL_ROOT / 'pending.json'
                self.assertEqual(json.loads(marker.read_text())['state'], 'pending')
                with self.assertRaisesRegex(self.g.GateError, 'pending'):
                    self.g.plan_release(str(self.proposal_path))
                with self.assertRaisesRegex(self.g.GateError, 'pending'):
                    self.g.apply(str(self.proposal_path), planned['approval_phrase'])
                self.assert_old()
                # Simulate owner clearance only in this isolated fixture, to test the other path.
                marker.unlink()
