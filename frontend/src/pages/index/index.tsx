import { View, Text } from "@tarojs/components"
import { useLoad } from "@tarojs/taro"
import { Button, Uploader } from "@nutui/nutui-react-taro"
import "./index.scss"

export default function Index () {
  useLoad(() => {
    console.log("Page loaded.")
  })

  return (
    <View className="index">
      <Text>Hello world!</Text>
      <Button type="primary">Gate 0 NutUI Button</Button>
      <Uploader />
    </View>
  )
}
