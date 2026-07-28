"""Fetcher 注册表。列表顺序即跨源去重时的优先级(靠前的源保留)。

hn 放最末:HN 帖为自由文本,同岗位若聚合站也收录,保留聚合站的结构化版本。
"""
from . import (remotive, weworkremotely, remoteok, jobicy, himalayas, workingnomads,
               hn_whoishiring, eleduck, v2ex, indeed_email, linkedin_email)

# 邮件源(indeed/linkedin)置于末位:链接是追踪跳转、结构性弱于聚合站,
# 跨源去重时优先级靠后(见 SPEC.md §27/§29)。
ALL_FETCHERS = [remotive, weworkremotely, remoteok, jobicy, himalayas, workingnomads,
                hn_whoishiring, eleduck, v2ex, indeed_email, linkedin_email]
