# gitcode 的 raw 走 CNB，不走 jsDelivr

`SOURCES["gitcode"].raw` 曾经是 `cdn.jsdelivr.net/gh`。jsDelivr 的 `/gh/` 读的是 GitHub，在大陆 DNS 污染后不稳定；GitCode 本身又屏蔽访客 raw 二进制，才被迫挂这层 CDN。

CNB（`cnb.cool/{repo}/-/git/raw/{ref}/{path}`）对公开仓匿名可读，不挡二进制。应用更新只把 raw（`versions.json`、`dist/packs/*.zip`）改到 CNB。`gitcode` 的 API / release 下载、四个附属仓、BT tracker 列表里别人的 jsDelivr 地址都不动。

key 仍叫 `gitcode`：China Source 没换，换的是它的 raw 宿主。竞速仍是先 200 的赢；过期但 200 的 CNB 可能在大陆赢过 GitHub，靠 `sha256` 和同一 job 里 `git push` CNB 把窗口压短。
