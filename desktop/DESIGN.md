# synkore · Motion & character / 1.1

保留暖灰纸面、墨绿文字与橙色主操作。动效表达层级、处理进度和角色回应，不增加营销落地页或改变现有三条工作流程。

## 动效节奏

- 主操作反馈：120–240ms；点击涟漪、轮廓光与轻微位移。
- 页面与分组切换：260–420ms；淡入、短距离上移，分组最多间隔45ms。
- 结果入场：每个结果ID只播放一次，流式增量更新不反复抖动。
- 导航：一个连续移动的选中背景；键盘焦点始终可见。
- 角色：弹性回弹、眼神、眨眼、微小呼吸；动作层与业务状态分离。
- 提供“灵动/轻柔”切换；系统减少动态效果的偏好始终优先。轻柔模式不使用粒子、惯性或持续漂浮。
- 页面隐藏时暂停渲染。粒子使用固定上限的对象池，避免持续增加GPU对象。

## 角色交互

- 鼠标跟随；3D射线识别脸、眼睛与头部。
- 拖动水平转身和轻微俯仰，释放时短暂惯性；触摸可用。
- 单击回应，双击开心；眼睛轻点会眨眼。
- 摸头：闭眼、轻微压缩回弹和暖色粒子。
- 击掌：伸出小手，抬起回应并出现短暂粒子。
- 休息/唤醒：闭眼与Z字，继续操作或开始业务时醒来。
- 聆听随输入音量轻微变化；播报使用实际PCM音量驱动嘴部。
- 完成轻轻庆祝，出错短暂困惑；不伪造模型回答，不冒充开放式AI聊天。

## 公开参考

本轮访问了用户提供的完整网址。第23项“motion-pri”缺少完整地址，未猜测其身份。

- [Scrolltide](https://www.scrolltide.co/templates)：角色视线与有叙事的运动；只研究公开介绍，未购买或复制付费模板。
- [Aceternity · 3D card](https://ui.aceternity.com/components/3d-card-effect)：悬停时的深度与视线反馈。
- [Magic UI · Blur Fade](https://magicui.design/docs/components/blur-fade) 与 [Ripple Button](https://magicui.design/docs/components/ripple-button)：短暂渐入、点击反馈。
- [shadcn/ui](https://ui.shadcn.com/docs/components/base/tooltip) 与 [Component Gallery](https://component.gallery/)：焦点与反馈的一致性。
- [minimal.gallery](https://minimal.gallery/)、[Refero](https://styles.refero.design/)、[land-book](https://land-book.com/)、[landing.love](https://www.landing.love/)、[hoverstat.es](https://www.hoverstat.es/)：留白、交互时机与角色表现。
- 同时检索 designmd.ai、vibeprompts.dev、kage.design、mobbin.com、navbar.gallery、footer.design、cta.gallery、supahero.io、pricingpages.design、21st.dev。定价页、页脚营销模块与当前课程工作室无直接需求，因此只参考可用的组件层次。
- godly.website 在访问时重定向到 recent.design，工具无法读取；awwwards.com 主页亦未能直接读取，没有声称完成这些站的逐页观察。

实现继续使用原有 Three.js、CSS 与 Web Animations API，未为动效加入新的运行依赖。
