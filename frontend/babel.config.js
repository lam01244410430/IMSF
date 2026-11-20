// babel-preset-taro 更多选项和默认值：
// https://docs.taro.zone/docs/next/babel-config
module.exports = {
  presets: [
    ["taro", {
      framework: "react",
      ts: true,
      compiler: "webpack5",
    }]
  ],
  plugins: [
    ["import", {
      libraryName: "@nutui/nutui-react-taro",
      libraryDirectory: "dist/es/packages",
      style: "css"
    }, "@nutui/nutui-react-taro"]
  ]
}
