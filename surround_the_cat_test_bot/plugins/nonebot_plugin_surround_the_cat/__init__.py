from nonebot import get_plugin_config
from nonebot import on_command
from nonebot import logger
from nonebot import get_driver
from nonebot.adapters import Bot
from nonebot.adapters import Message
from nonebot.adapters.console import Bot as ConsoleBot
from nonebot.adapters.console import MessageSegment as ConsoleMessageSegment
from nonebot.adapters.onebot.v11 import Bot as OnebotBot
from nonebot.adapters.onebot.v11.message import MessageSegment as OnebotMessageSegment
from nonebot.adapters.onebot.v11 import PrivateMessageEvent, GroupMessageEvent
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq.event import GroupMsgReceiveEvent
from nonebot.matcher import Matcher
from nonebot.typing import T_State
from nonebot.params import ArgPlainText, CommandArg, Depends
from nonebot.plugin import PluginMetadata
import requests
import threading
import os
import random
import inspect
import signal
from PIL import Image, ImageDraw
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="nonebot-plugin-surround-the-cat",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)
driver = get_driver()


running = True
cachePictureList = set()
usingPictureMap = {}
updatePictureList = set()
# 条件变量，用于生产者等待消费者消费数据后开始执行
condition = threading.Condition()

os.makedirs(config.imageCacheDirectory, exist_ok=True)


def checkAndAddToCache():
    """
    检查指定路径下的文件是否存在，如果存在，则将其添加到缓存图片列表中。
    """
    for i in range(0, config.imageCacheCount):
        path = f"{config.imageCacheDirectory}/{i}.jpg"
        if (
            len(cachePictureList) < 5
            or len(cachePictureList) < config.imageCacheCount / 2
        ):
            if os.path.exists(path):
                cachePictureList.add(path)
            else:
                updatePictureList.add(path)
        else:
            updatePictureList.add(path)


def downloadPicture():
    global running
    while running:
        # 发送 HTTP GET 请求
        url = "https://api.lolicon.app/setu/v2"
        response = requests.get(url)

        # 检查请求是否成功
        if response.status_code == 200:
            # 解析 JSON 数据
            json_data = response.json()
            downloadImage(json_data["data"][0]["urls"]["original"])


def downloadImage(url):
    # 发送 HTTP GET 请求获取图片数据
    response = requests.get(url)

    # 检查请求是否成功
    if response.status_code == 200:
        # 获取条件变量的锁
        with condition:
            while len(updatePictureList) <= 0:
                # 如果缓存图片列表已满，则等待消费者消费一个数据
                condition.wait()
            localPath = updatePictureList.pop()
            # 将图片数据写入本地文件
            with open(localPath, "wb") as file:
                file.write(response.content)
            cachePictureList.add(localPath)
            logger.debug(f"图片下载成功，已保存到 {localPath}")


def downloadImageToDirectory(url, localPath):
    # 发送 HTTP GET 请求获取图片数据
    response = requests.get(url)

    # 检查请求是否成功
    if response.status_code == 200:
        # 将图片数据写入本地文件
        with open(localPath, "wb") as file:
            file.write(response.content)
        logger.debug(f"图片下载成功，已保存到 {localPath}")


def randomJpgFile(directory):
    """
    从指定目录中随机选择一个后缀名为 .jpg 的文件，并返回文件名。

    参数：
    directory (str): 目录路径。

    返回：
    str: 随机选择的 .jpg 文件名，如果目录中不存在 .jpg 文件，则返回 None。
    """

    # 获取目录下所有指定后缀名为 .jpg 的文件
    jpg_files = [file for file in os.listdir(directory) if file.endswith(".jpg")]

    if jpg_files:
        # 随机选择一个文件
        random_jpg_file = random.choice(jpg_files)
        return random_jpg_file
    else:
        logger.error(f"{directory}目录中不存在 .jpg 文件")
        return None


def randomFile():
    with condition:
        if len(cachePictureList) <= 0:
            logger.warning(
                f"缓存图片数量不足，需要增加缓存数量，修改.env文件，设置IMAGE_CACHE_COUNT，当前缓存数量为{config.imageCacheCount}"
            )
            condition.notify_all()
            return f"{config.imageCacheDirectory}/{randomJpgFile(config.imageCacheDirectory)}"
        choiceRandomFile = cachePictureList.pop()
        condition.notify_all()
        return choiceRandomFile


def resizeImage(imagePath, newWidth, newHeight):
    # 读取图片
    image = Image.open(imagePath).convert("RGBA")
    # 创建一个与原始图片尺寸相同的白色背景
    whiteBackground = Image.new("RGBA", image.size, "white")
    # 将原始图片叠加在白色背景上，透明部分会被白色背景覆盖
    resultImage = Image.alpha_composite(whiteBackground, image)

    # 缩放图片
    new_size = (newWidth, newHeight)

    return resultImage.resize(new_size)


def drawPicture(headImagePath):
    # 创建一个 300x300 的白色图片
    image = Image.new("RGB", (500, 418), (179, 217, 254))

    # 创建绘图对象
    draw = ImageDraw.Draw(image)

    r = 25
    for j in range(1, 10):
        for i in range(1, 10):
            x = (r * 2 + 2) * i + 2 - r
            y = (r * 2 - 5) * j + 9 - r
            if j % 2 == 0:
                x = x + r
            textX = x - r + 5
            textY = y - r + 4
            if j == 1:
                textX = x - r / 2 + 2
            # 使用默认字体写文本
            draw.text((textX, textY), f"{i+(j-1)*9}", fill="black", font_size=35)
            draw.ellipse((x - r, y - r, x + r, y + r), outline="black", width=3)
    # 绘制图片
    # draw.bitmap((0, 0), resizeAndMaskImage(headImagePath,50,50))
    newWidth = r*2-4
    newHeight = r*2-4
    processed_image = resizeImage(headImagePath, newWidth, newHeight)

    # 创建一个与缩放后图片大小相同的黑色背景
    mask = Image.new("L", (newWidth, newHeight), 0)

    index=72
    indexToI=(index-1)%9+1
    indexToJ=(index-1)//9+1
    indexToX = (r * 2 + 2) * indexToI + 2 - r*2+2
    indexToY = (r * 2 - 5) * indexToJ + 9 - r*2+2
    if indexToJ % 2 == 0:
        indexToX = indexToX + r
    # 在黑色背景上绘制一个白色的圆形，作为遮罩
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, newWidth, newHeight), fill=255)
    image.paste(processed_image, (indexToX, indexToY), mask=mask)
    # 绘制一个黑色圆形
    # draw.ellipse((50, 50, 250, 250))

    # 保存图片
    image.save(f"{config.imageCacheDirectory}/circle_image.png")


downloadImageToDirectory(
    "https://marketplace.canva.cn/PX2nY/MAA9p7PX2nY/4/tl/canva-user--MAA9p7PX2nY.png",
    f"{config.imageCacheDirectory}/common-user.png",
)
checkAndAddToCache()
# 创建后台线程
background_thread = threading.Thread(target=downloadPicture)
background_thread.daemon = True  # 将线程设置为守护线程，使程序退出时自动结束
background_thread.start()

drawPicture(f"{config.imageCacheDirectory}/common-user.png")

surroundTheCat = on_command("围猫咪", priority=10)

@driver.on_shutdown
async def shutdown():
    global running
    running=False
    with condition:
        condition.notify_all()

@surroundTheCat.handle()
async def handle_function(state: T_State):
    state["picturePath"] = randomFile()


# 通过依赖注入或事件处理函数来进行业务逻辑处理


# 处理控制台回复
@surroundTheCat.handle()
async def handle_console_reply(bot: ConsoleBot, state: T_State):
    key = "console"
    if key in usingPictureMap:
        with condition:
            updatePictureList.add(usingPictureMap[key])
    usingPictureMap[key] = state["picturePath"]
    await surroundTheCat.finish(state["picturePath"])


# 处理 OneBot 私聊回复
@surroundTheCat.handle()
async def handle_onebot_private_reply(
    bot: OnebotBot, event: PrivateMessageEvent, state: T_State
):
    key = f"private-{event.user_id}"
    if key in usingPictureMap:
        with condition:
            updatePictureList.add(usingPictureMap[key])

    usingPictureMap[key] = state["picturePath"]
    await surroundTheCat.finish(state["picturePath"])


# 处理 OneBot 群聊回复
@surroundTheCat.handle()
async def handle_onebot_group_reply(
    bot: OnebotBot, event: GroupMessageEvent, state: T_State
):
    key = f"group-{event.group_id}"
    if key in usingPictureMap:
        with condition:
            updatePictureList.add(usingPictureMap[key])
    usingPictureMap[key] = state["picturePath"]
    await surroundTheCat.finish(state["picturePath"])


# 兼容性处理
@surroundTheCat.handle()
async def handle_onebot_group_reply(bot, event, state: T_State):
    with condition:
        cachePictureList.add(state["picturePath"])


# @surroundTheCat.handle()
# async def handle_function():
#     await surroundTheCat.finish(f"{config.imageCacheDirectory}/{randomJpgFile(config.imageCacheDirectory)}")
#
# @surroundTheCat.handle()
# async def handle_private(event: PrivateMessageEvent):
#     await surroundTheCat.finish("私聊消息")
#
# @surroundTheCat.handle()
# async def handle_group(event: GroupMessageEvent):
#     await surroundTheCat.finish("群聊消息")
