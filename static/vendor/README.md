# static/vendor 放本地第三方静态资源（负责人：P5）

离线答辩环境不保证能连公网，演示前请把 ECharts 下载到本目录：

```bash
# 任选其一
curl -L -o static/vendor/echarts.min.js https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js
# 或浏览器打开上面链接，右键"另存为"到本目录
```

`templates/base.html` 先加载本目录的 `echarts.min.js`，加载失败才回退到 CDN，
所以本地放好之后，断网也能演示关系图。

本文件与 `echarts.min.js` 一起提交到仓库（约 1 MB，可接受）。
