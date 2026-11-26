# static/vendor 放本地第三方静态资源（负责人：P5）

## 已入库

| 文件 | 版本 | 大小 | 来源 |
|---|---|---|---|
| `echarts.min.js` | 5.5.1（UMD 压缩版） | 约 1.0 MB | https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js |

`templates/base.html` 先加载本目录的 `echarts.min.js`，加载失败才回退到 CDN，
所以文件在仓库里，**断网也能渲染关系图**，答辩不依赖外网。

## 拉取后校验

大小不对通常说明下载被截断或存成了 HTML 错误页：

```bash
ls -l static/vendor/echarts.min.js            # 约 1007 KB
md5sum static/vendor/echarts.min.js           # ef12c5c63df2acdf59f8a86cf0317711
grep -o 'version="5.5.1"' static/vendor/echarts.min.js | head -1
```

## 升级

只在有明确需要时升级，并同步改本文件的版本号：

```bash
curl -L -o static/vendor/echarts.min.js https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js
```

不要把未压缩的 `echarts.js`（约 3 MB）放进仓库；排查问题时临时使用，不要提交。
