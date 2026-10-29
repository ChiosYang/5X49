"""Synthetic neighboring expressions; no diagnostic questions or answers."""
import unittest
from app.services.content_request import split_content_request


class ContentFocusRegressionTests(unittest.TestCase):
    def test_story_contrast_does_not_require_a_specific_particle(self):
        for particle in ('那部','的那部','这一部','的这一部'):
            for subject in ('老师逼迫学生练字','外地侦探','乡村医生'):
                q='不是'+subject+particle+'。我找的是两位邻居一起修房子的故事。'
                with self.subTest(question=q):
                    r=split_content_request(q)
                    self.assertIsNone(r.issue,r)
                    self.assertIn(subject,r.text)
                    self.assertEqual(r.hard.exclude_countries,[])

    def test_reference_like_role_is_not_a_production_fact(self):
        for q in ('想看一位记者寻找失散亲人的故事，不是城里律师那部。',
                  '重点是朋友之间的照顾，不是追逐复仇。',
                  '主要关注人物关系，不是破案解谜故事。',
                  '想看一个作家的故事，写作不是装饰，而是他理解世界的方式。',
                  '想看邻居互助的故事，友谊并非陪衬，而是改变他们生活的力量。'):
            with self.subTest(question=q):
                r=split_content_request(q)
                self.assertIsNone(r.issue,r)
                self.assertTrue(r.text)

    def test_complete_role_contrast_still_rejects_metadata_and_inner_bans(self):
        for tail in ('不是日本的那部','不是科幻的那部','不是法国制作的警察那部',
                     '不是某人主演的医生那部','不是片长90分钟的侦探那部',
                     '不是没有暴力的警察那部','不是医生那部但必须没有暴力',
                     '不是律师那部但是只要日本电影'):
            with self.subTest(tail=tail):
                self.assertIsNotNone(split_content_request('想看家庭团聚的故事，'+tail).issue)

    def test_focus_correction_is_not_a_general_negation_escape(self):
        for q in ('想看邻居的故事，不是谋杀。',
                  '重点是人与关系，不是恐怖类型。',
                  '重点是人与关系，不是日本拍摄的追凶故事。',
                  '想看家庭，国家不是背景，而是日本。',
                  '想看一个人的故事，导演不是陪衬，而是某人。',
                  '重点是家人，不是追凶但必须没有暴力。',
                  '想看邻居故事，友谊不是装饰，而是必须没有暴力。'):
            with self.subTest(question=q):
                self.assertIsNotNone(split_content_request(q).issue)

    def test_conjoined_no_substitute_control_needs_a_bound_person(self):
        for prefix in ('也','但','并且','而且'):
            q='films directed by Another Person about a rescue, '+prefix+'不要换导演凑数'
            with self.subTest(prefix=prefix):
                r=split_content_request(q)
                self.assertIsNone(r.issue,r)
                self.assertEqual([(p.name,p.role) for p in r.hard.people],[('Another Person','director')])
                self.assertIsNotNone(split_content_request('films about a rescue, '+prefix+'不要换导演凑数').issue)

    def test_new_hard_clause_after_correction_never_disappears(self):
        for frame in ('重点是亲人，不是复仇','音乐不是装饰，而是人物生活的一部分'):
            for join in ('但是','并且','而且'):
                for space in ('',' ','\t'):
                    q='想看家庭故事，'+frame+join+space+'必须没有暴力'
                    with self.subTest(question=q):
                        self.assertIsNotNone(split_content_request(q).issue)


if __name__=='__main__':unittest.main()
