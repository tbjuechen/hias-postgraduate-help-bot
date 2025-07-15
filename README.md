# 杭高院考研群BOT

> 🔥报考杭高院=坐拥顶配人生！国科大杭高院携杭州C位buff强势招生——22408考试科目简单易学，零基础也能轻松拿捏！学术资源卷到天花板，杰青院士面对面带飞，计算机/软件所/网络中心三大王牌赛道任选，保科研冲大厂双开挂！AI方向25年招生简章仅27人，最终录取暴增至78人，扩招红利直接拉满！地铁12号线直达西子湖畔，课间就能打卡"西湖十景"，食堂更狂撒500万补贴，月花600-800吃遍杭帮菜+网红美食，这波"学术天堂+生活乐园"的王炸组合谁能拒绝？坐标全国互联网中心，大厂实习步行可达，中科院光环加持华5级就业，现在扫码进群817445354，解锁抄底上岸密码，26届本科er速冲这趟"学术暴富"专列！🚀

国科大杭高院智能学院AI/CS方向考研群机器人

群号：817445354

## 插件列表


| 插件名                                                                           | 用途                     |
| -------------------------------------------------------------------------------- | ------------------------ |
| [nonebot_plugin_resolver2](https://github.com/fllesser/nonebot-plugin-resolver2) | 解析链接、卡片等         |
| [nonebot_plugin_status](https://github.com/nonebot/plugin-status)                | 查看服务器状态           |
| [nonebot-plugin-wordcloud](https://github.com/he0119/nonebot-plugin-wordcloud)   | 词云统计                 |
| [ping-pong](#ping-pong)                                                          | 机器人在线查询           |
| [water-time](#water-time)                                                        | 群成员水群时间提醒、统计 |
| [hias-qa](#hias-qa)                                                              | 杭高问答                 |
| [group_msg_collect](#group_msg_collect)                                          | 群聊消息收集             |
| [summary](#summary)                                                              | 省流                     |
| [new_member](#new_member)                                                        | 入群审批、欢迎           |
| [repeat](#repeat)                                                                | 应声虫                   |
| [help](#help)                                                                    | 帮助菜单                 |
| [info](#info)                                                                    | 机器人信息               |

注：第一方插件均受 `allowed_group`环境变量控制。

### ping-pong

使用方法：

/ping 或者 ~~@机器人 ping~~

机器人会回复pong

### water-time

使用方法：

/stats  [@成员] 或 /水群统计

在没有@成员时返回水群日榜前十，当@成员时返回指定成员的水群统计

当成员日水群时间到达60、120、180等节点会发出提醒

### hias-qa

使用方法：

/hias <问题> 或 /杭高问答 或 直接@机器人

~~机器人~~学姐会根据[文档](./src/docs/（QA）杭高智能报考指南v1.3.0（20250518）.pdf)内容回答成员关于杭高院的问题

### group_msg_collect

内置插件，用于收集群聊记录并提供api给下游插件，无需显式调用。

### summary

使用方法：

/省流 或 /总结 或 /summary

总结近群聊内近10分钟或近100条消息（取其一），并转化为图片输出到群聊。

### new_member

新成员自动审批（关键字匹配）+欢迎

### repeat

应声虫有20%的概率协战，但是如果你打一行字，我会有100%的概率复制你。

应声虫有20%的概率协战，但是如果你打一行字，我会有100%的概率复制你。

应声虫有20%的概率协战，但是如果你打一行字，我会有100%的概率复制你。

### hlep

使用方法：

/help 或 /帮助 输出插件列表

/help <插件名> 输出插件使用方法

### info

使用方法：

/info 或 /信息 输出机器人当前版本和信息

## 环境变量

可能需要用到的环境变量，如需查看完整环境变量，请查看nonebot文档和第三方插件仓库。


| 变量名              | 是否必须 | 备注                                                                                                   |
| ------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| HOST                | 否       | ws服务地址                                                                                             |
| PORT                | 否       | ws服务端口                                                                                             |
| ONEBOT_ACCESS_TOKEN | 否       | ws服务token                                                                                            |
| r_use_base64        | 否       | 默认为`false`，`nonebot_plugin_resolver2`是否使用 `base64`输出，当适配器为 `napcat`时建议设置为 `true` |
| SUPERUSERS          | 否       | 超级用户列表                                                                                           |
| OPENAI_API_BASE     | 否       | 大模型api地址，默认为`deepseek`                                                                        |
| OPENAI_API_KEY      | 是       | 大模型api密钥                                                                                          |
| OPENAI_MODEL        | 否       | 选用的模型，默认为`deepseek-chat`                                                                      |
| allowed_groups      | 是       | 第一方插件启用群聊列表                                                                                 |

## 部署

~~想必也没有人会想部署的~~

以下提供一个在 `Debian`系统上的基于 `docker`的部署方式

### 1. 安装驱动器（以[NapCat](https://github.com/NapNeko/NapCatQQ)为例）

根据官方文档操作，运行NapCat容器并登陆账号：

```bash
docker run -d \
-e NAPCAT_GID=$(id -g) \
-e NAPCAT_UID=$(id -u) \
-p 3000:3000 \
-p 3001:3001 \
-p 6099:6099 \
--name napcat \
--restart=always \
mlikiowa/napcat-docker:latest
```

### 2. 安装依赖

```bash
git clone https://github.com/tbjuechen/qq-water-bot.git
cd qq-water-bot
pip install -r requirements.txt

# ffmpeg安装（可选）
sudo apt-get update
sudo apt-get install ffmpeg
```

### 3. 运行bot

```bash
python3 bot.py
```

然后在 `NapCat`中填写ws服务器地址与密钥连接bot。

## ~~未来规划~~ 画饼

* [X]  hias_qa 插件知识库+文本嵌入实现
* [ ]  闲聊插件（动态上下文实现）
* [X]  help插件（现在这个太丑）
* [X]  water_time 插件启动后根据数据库中内容获得今日水群状态表
* [ ]  ~~解决 hias_qa 莫名其妙在一个群失效的bug~~（也许不是bug，只是没有at）
* [ ]  解决 summary 插件换行以及emjoy乱码的问题
* [X]  hias_qa 插件使用回复链作为上下文，而并非仅有当前消息
* [ ]  ~~热更新~~
* [ ]  自动ban逆天言论 **enhancement**
