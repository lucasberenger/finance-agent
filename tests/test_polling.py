import unittest
from unittest.mock import Mock

import httpx

from app.polling import TelegramPoller


def response(data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request('GET', 'https://example.test'))


def update(update_id, owner=123):
    return {'update_id': update_id, 'message': {'chat': {'id': owner, 'type': 'private'},
            'from': {'id': owner}, 'text': '/resumo'}}


class PollingTests(unittest.TestCase):
    def setUp(self):
        self.poller = TelegramPoller('test-token', 123, 'test-secret')
        self.telegram, self.local = Mock(), Mock()
        self.local.post.return_value = response({'ok': True})

    def test_forwards_owner_and_confirms_success(self):
        self.telegram.get.return_value = response({'ok': True, 'result': [update(10)]})
        self.poller.poll_once(self.telegram, self.local)
        self.assertEqual(self.poller.offset, 11)
        self.local.post.assert_called_once_with('http://127.0.0.1:8000/telegram/webhook',
            json=update(10), headers={'X-Telegram-Bot-Api-Secret-Token': 'test-secret'})
        self.poller.poll_once(self.telegram, self.local)
        self.assertEqual(self.telegram.get.call_args.kwargs['params']['offset'], 11)

    def test_failure_keeps_failed_message_and_remaining_batch_pending(self):
        self.telegram.get.return_value = response({'ok': True, 'result': [update(10), update(11), update(12)]})
        self.local.post.side_effect = [response({'ok': True}), response({}, 503)]
        with self.assertRaises(httpx.HTTPStatusError):
            self.poller.poll_once(self.telegram, self.local)
        self.assertEqual(self.poller.offset, 11)
        self.assertEqual(self.local.post.call_count, 2)

    def test_skips_other_users(self):
        self.telegram.get.return_value = response({'ok': True, 'result': [update(10, 999)]})
        self.poller.poll_once(self.telegram, self.local)
        self.local.post.assert_not_called()
        self.assertEqual(self.poller.offset, 11)

    def test_refuses_existing_webhook_without_changing_it(self):
        self.local.get.return_value = response({'ok': True})
        self.telegram.get.return_value = response({'ok': True, 'result': {'url': 'https://example.test'}})
        with self.assertRaises(ValueError):
            self.poller.check(self.telegram, self.local)
        self.assertEqual(self.telegram.get.call_count, 1)
        self.local.post.assert_not_called()

    def test_api_error_does_not_confirm_updates(self):
        self.telegram.get.return_value = response({'ok': False}, 401)
        with self.assertRaises(httpx.HTTPStatusError):
            self.poller.poll_once(self.telegram, self.local)
        self.assertIsNone(self.poller.offset)
        self.local.post.assert_not_called()
