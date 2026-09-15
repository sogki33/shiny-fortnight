import unittest
from unittest.mock import patch
import automation as a


class QueueSafetyTests(unittest.TestCase):
    def sample(self):
        return {'id':'one','status':'approved','reviewed_by':'editor',
            'text':'계정 소개', 'media_type':'IMAGE',
            'media_url':'https://example.com/photo.png','media_rights':'original'}

    def test_missing_image_blocks(self):
        item=self.sample(); item['media_url']=''
        with self.assertRaises(ValueError): a.validate(item)

    def test_future_post_does_not_publish(self):
        item = self.sample(); item['not_before'] = '2099-01-01T08:30:00+09:00'
        with patch.object(a,'read',side_effect=[[item],{}]), patch.object(a,'api') as api, patch.object(a,'persist') as persist:
            a.publish()
            api.assert_not_called(); persist.assert_not_called()

    def test_schedule_requires_timezone(self):
        item = self.sample(); item['not_before'] = '2026-09-16T08:30:00'
        with patch.object(a,'read',side_effect=[[item],{}]):
            with self.assertRaises(ValueError): a.publish()

    def test_ad_requires_disclosure_and_link(self):
        item=self.sample(); item['affiliate_url']='https://link.coupang.com/a/test'
        with self.assertRaises(ValueError): a.validate(item)
        item['text'] += '\n'+a.DISCLOSURE+'\n'+item['affiliate_url']
        self.assertTrue(a.validate(item))

    def test_ambiguous_previous_publish_blocks_network(self):
        with patch.object(a,'read',side_effect=[[self.sample()],{'old':{'phase':'publishing'}}]), patch.object(a,'api') as api:
            with self.assertRaises(RuntimeError): a.publish()
            api.assert_not_called()

    def test_dry_run_never_calls_network_or_persist(self):
        with patch.object(a,'read',side_effect=[[self.sample()],{}]), patch.object(a,'api') as api, patch.object(a,'persist') as persist:
            a.publish(dry_run=True)
            api.assert_not_called(); persist.assert_not_called()

    def test_already_published_is_skipped(self):
        with patch.object(a,'read',side_effect=[[self.sample()],{'one':{'phase':'published'}}]), patch.object(a,'api') as api:
            a.publish(); api.assert_not_called()
