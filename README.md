# 杭高院考研群BOT

## 插件列表


| 插件名                                                                           | 用途                     |
| -------------------------------------------------------------------------------- | ------------------------ |
| [nonebot_plugin_resolver2](https://github.com/fllesser/nonebot-plugin-resolver2) | 解析链接、卡片等         |
| [nonebot_plugin_status](https://github.com/nonebot/plugin-status)                | 查看服务器状态           |
| [nonebot_plugin_treehelp](https://github.com/he0119/nonebot-plugin-treehelp)     | 查看bot功能              |
| [nonebot-plugin-wordcloud](https://github.com/he0119/nonebot-plugin-wordcloud)   | 词云统计                 |
| [ping-ping](#ping-pong)                                                          | 机器人在线查询           |
| [water-time](#water-time)                                                        | 群成员水群时间提醒、统计 |
| [hias-qa](#hias-qa)                                                              | 杭高问答                 |

### ping-pong

使用方法：

/ping 或者 @机器人 ping

机器人会回复pong

### water-time

使用方法：

/stats  [@成员]

在没有@成员时返回水群日榜前十，当@成员时返回指定成员的水群统计

当成员日水群时间到达60、120、180等节点会发出提醒

### hias-qa

使用方法：

/hias <问题>

机器人会根据[文档](./src/（QA）杭高智能报考指南v1.3.0（20250518）.pdf)内容回答成员关于杭高院的问题
