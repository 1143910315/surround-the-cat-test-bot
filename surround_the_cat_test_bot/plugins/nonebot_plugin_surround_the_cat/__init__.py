from nonebot import get_plugin_config
from nonebot import on_command
from nonebot import logger
from nonebot import get_driver
from nonebot import on_regex
from nonebot.adapters import Bot
from nonebot.adapters import Event
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
from datetime import datetime, timedelta
import threading
import os
from collections import deque
import networkx as nx
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
playerGameDataMap = {}
updatePictureList = set()
# 条件变量，用于生产者等待消费者消费数据后开始执行
condition = threading.Condition()
exitList = []
mapWidth = 9
mapHeight = 9
for i in range(1, mapWidth + 1):
    exitList.append(i)
    exitList.append(mapWidth * mapHeight - mapWidth + i)
for j in range(2, mapHeight):
    exitList.append(mapWidth * (j - 1) + 1)
    exitList.append(mapWidth * j)


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
                cachePictureList.add(f"{i}.jpg")
            else:
                updatePictureList.add(f"{i}.jpg")
        else:
            updatePictureList.add(f"{i}.jpg")


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
            fileName = updatePictureList.pop()
            localPath = f"{config.imageCacheDirectory}/{fileName}"
            # 将图片数据写入本地文件
            with open(localPath, "wb") as file:
                file.write(response.content)
            cachePictureList.add(fileName)
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

    # 获取目录下所有指定后缀名为 .jpg 的文件，并且文件名不包含下划线
    jpg_files = [
        file
        for file in os.listdir(directory)
        if file.endswith(".jpg") and "_" not in file
    ]

    if jpg_files:
        # 随机选择一个文件
        randomJpgFile = random.choice(jpg_files)
        return randomJpgFile
    else:
        logger.error(f"{directory}目录中不存在 .jpg 文件")
        return None


def generateUniqueFilename(directory, prefix, fileName):
    randomInt = random.randint(1, 10000)
    newFilename = os.path.join(directory, f"{prefix}_{randomInt}_{fileName}")
    while os.path.exists(newFilename):
        randomInt += 1
        newFilename = os.path.join(directory, f"{prefix}_{randomInt}_{fileName}")
    return newFilename


def randomFile():
    with condition:
        if len(cachePictureList) <= 0:
            logger.warning(
                f"缓存图片数量不足，需要增加缓存数量，修改.env文件，设置IMAGE_CACHE_COUNT，当前缓存数量为{config.imageCacheCount}"
            )
            condition.notify_all()
            fileName = randomJpgFile(config.imageCacheDirectory)
            if fileName == None:
                logger.error(f"{config.imageCacheDirectory} 目录下无图片可用")
                return ""
            # 新文件名
            newFilename = generateUniqueFilename(
                config.imageCacheDirectory, "in_game", fileName
            )
            os.rename(f"{config.imageCacheDirectory}/{fileName}", newFilename)
            return newFilename
        while len(cachePictureList) > 0:
            fileName = cachePictureList.pop()
            choiceRandomFile = f"{config.imageCacheDirectory}/{fileName}"
            updatePictureList.add(fileName)
            if os.path.exists(choiceRandomFile):
                # 新文件名
                newFilename = generateUniqueFilename(
                    config.imageCacheDirectory, "in_game", fileName
                )
                os.rename(choiceRandomFile, newFilename)
                condition.notify_all()
                return newFilename
        logger.warning(
            f"缓存图片数量不足，需要增加缓存数量，修改.env文件，设置IMAGE_CACHE_COUNT，当前缓存数量为{config.imageCacheCount}(此处逻辑应当不会执行，看见此条输出可以联系开发者)"
        )
        condition.notify_all()
        fileName = randomJpgFile(config.imageCacheDirectory)
        if fileName == None:
            logger.error(
                f"{config.imageCacheDirectory} 目录下无图片可用(此处逻辑应当不会执行，看见此条输出可以联系开发者)"
            )
            return ""
        choiceRandomFile = f"{config.imageCacheDirectory}/{fileName}"
        randomInt = random.randint(1, 10000)
        # 新文件名
        newFilename = f"{config.imageCacheDirectory}/in_game_{randomInt}_{fileName}"
        while os.path.exists(newFilename):
            randomInt = randomInt + 1
            newFilename = f"{config.imageCacheDirectory}/in_game_{randomInt}_{fileName}"
        os.rename(choiceRandomFile, newFilename)
        return newFilename


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


def fromIndexToIJ(index):
    return ((index - 1) % 9 + 1, (index - 1) // 9 + 1)


def fromIJToIndex(i, j):
    return i + (j - 1) * 9


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
    newWidth = r * 2 - 4
    newHeight = r * 2 - 4
    processed_image = resizeImage(headImagePath, newWidth, newHeight)

    # 创建一个与缩放后图片大小相同的黑色背景
    mask = Image.new("L", (newWidth, newHeight), 0)

    index = 72
    indexToI = (index - 1) % 9 + 1
    indexToJ = (index - 1) // 9 + 1
    indexToX = (r * 2 + 2) * indexToI + 2 - r * 2 + 2
    indexToY = (r * 2 - 5) * indexToJ + 9 - r * 2 + 2
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


def checkGameLive(gameData):
    # 获取当前时间
    current_time = datetime.now()

    # 计算与另一个时间的间隔
    time_difference = current_time - gameData["lastUpdateTime"]

    # 判断间隔是否大于 3 分钟
    if time_difference > timedelta(minutes=3):
        print("间隔大于3分钟")


def recyclingGameData(gameData):
    catList = gameData["catList"]
    for cat in catList:
        os.remove(cat["catPicture"])


def initGame():
    map = {}
    playerList = []
    catList = []
    createGameSuccess = True
    for i in range(1, 10):
        map[i] = {}
        for j in range(1, 10):
            map[i][j] = {"status": 0}
            serialNumber = i + (j - 1) * 9
            if serialNumber in [31, 32, 40, 41, 42, 49, 50]:
                if len(catList) < 5:
                    if random.random() < 0.4:
                        catPicture = randomFile()
                        if bool(catPicture):
                            map[i][j]["status"] = 3
                            catList.append(
                                {
                                    "i": i,
                                    "j": j,
                                    "catPicture": catPicture,
                                    "algorithm": random.randint(1, 1),
                                    "status": 0,
                                }
                            )
            else:
                if random.random() < 0.12:
                    map[i][j]["status"] = 1
    if len(catList) == 0:
        firstSerialNumber = random.choice([31, 32, 40, 41, 42, 49, 50])
        positonIJ = fromIndexToIJ(firstSerialNumber)
        catPicture = randomFile()
        if bool(catPicture):
            catList.append(
                {
                    "i": positonIJ[0],
                    "j": positonIJ[1],
                    "catPicture": catPicture,
                    "algorithm": random.randint(1, 1),
                    "status": 0,
                }
            )
        else:
            createGameSuccess = False
    return {
        "map": map,
        "playerList": playerList,
        "catList": catList,
        "lastUpdateTime": datetime.now(),
        "createGameSuccess": createGameSuccess,
    }


def createGraphFromGamedata(gameData):
    # 使用 NetworkX 创建图形结构
    graph = nx.Graph()
    map = gameData["map"]
    for index in range(1, 82):
        i, j = fromIndexToIJ(index)
        if map[i][j]["status"] == 0:
            if i + 1 < 10 and map[i + 1][j]["status"] == 0:
                newIndex = fromIJToIndex(i + 1, j)
                graph.add_edge(index, newIndex)
            if j % 2 == 0:
                if i + 1 < 10 and j + 1 < 10 and map[i + 1][j + 1]["status"] == 0:
                    newIndex = fromIJToIndex(i + 1, j + 1)
                    graph.add_edge(index, newIndex)
            else:
                if i - 1 > 0 and j + 1 < 10 and map[i - 1][j + 1]["status"] == 0:
                    newIndex = fromIJToIndex(i - 1, j + 1)
                    graph.add_edge(index, newIndex)
            if j + 1 < 10 and map[i][j + 1]["status"] == 0:
                newIndex = fromIJToIndex(i, j + 1)
                graph.add_edge(index, newIndex)
    return graph


def bfsShortestPath(gameData, startNode):
    # 使用广度优先搜索算法找到从起点到所有出口的最短路径
    shortestPaths = nx.shortest_path(
        createGraphFromGamedata(gameData), source=startNode
    )
    shortestPaths = {
        key: value for key, value in shortestPaths.items() if key in exitList
    }
    if len(shortestPaths) == 0:
        return []
    # 找到最短路径中最短的那条路径
    shortest_exit = min(shortestPaths, key=lambda x: len(shortestPaths[x]))

    return shortestPaths[shortest_exit]


def moveAllCat(gameData):
    map = gameData["map"]
    catList = gameData["catList"]
    for cat in catList:
        if cat["status"] == 0:
            catI = cat["i"]
            catJ = cat["j"]
            map[catI][catJ]["status"] = 0
            catAlgorithm = cat["algorithm"]
            if catAlgorithm == 1:
                path = bfsShortestPath(gameData, fromIJToIndex(catI, catJ))
                if len(path) > 1:
                    i, j = fromIndexToIJ(path[1])
                    cat["i"] = i
                    cat["j"] = j
                    if path[1] in exitList:
                        cat["status"] = -1
                    else:
                        map[i][j]["status"] = 3
                else:
                    cat["status"] = 1


def drawGameData(gameData, userImage):
    map = gameData["map"]
    catList = gameData["catList"]
    playerList = gameData["playerList"]
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
            if map[i][j]["status"] == 0:
                textX = x - r + 5
                textY = y - r + 4
                if j == 1:
                    textX = x - r / 2 + 2
                # 使用默认字体写文本
                draw.text((textX, textY), f"{i+(j-1)*9}", fill="black", font_size=35)
                draw.ellipse((x - r, y - r, x + r, y + r), outline="black", width=3)
            elif map[i][j]["status"] == 1:
                draw.ellipse((x - r, y - r, x + r, y + r), fill="black", width=3)

    for cat in catList:
        if cat["status"] == 0:
            imagePath = cat["catPicture"]
            indexToI = cat["i"]
            indexToJ = cat["j"]
            # 绘制图片
            # draw.bitmap((0, 0), resizeAndMaskImage(headImagePath,50,50))
            newWidth = r * 2 - 4
            newHeight = r * 2 - 4
            processed_image = resizeImage(imagePath, newWidth, newHeight)

            # 创建一个与缩放后图片大小相同的黑色背景
            mask = Image.new("L", (newWidth, newHeight), 0)

            indexToX = (r * 2 + 2) * indexToI + 2 - r * 2 + 2
            indexToY = (r * 2 - 5) * indexToJ + 9 - r * 2 + 2
            if indexToJ % 2 == 0:
                indexToX = indexToX + r
            # 在黑色背景上绘制一个白色的圆形，作为遮罩
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, newWidth, newHeight), fill=255)
            image.paste(processed_image, (indexToX, indexToY), mask=mask)
    for positionIndex in playerList:
        position = fromIndexToIJ(positionIndex)
        imagePath = userImage
        indexToI = position[0]
        indexToJ = position[1]
        # 绘制图片
        # draw.bitmap((0, 0), resizeAndMaskImage(headImagePath,50,50))
        newWidth = r * 2 - 4
        newHeight = r * 2 - 4
        processed_image = resizeImage(imagePath, newWidth, newHeight)

        # 创建一个与缩放后图片大小相同的黑色背景
        mask = Image.new("L", (newWidth, newHeight), 0)

        indexToX = (r * 2 + 2) * indexToI + 2 - r * 2 + 2
        indexToY = (r * 2 - 5) * indexToJ + 9 - r * 2 + 2
        if indexToJ % 2 == 0:
            indexToX = indexToX + r
        # 在黑色背景上绘制一个白色的圆形，作为遮罩
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, newWidth, newHeight), fill=255)
        image.paste(processed_image, (indexToX, indexToY), mask=mask)

    # 绘制一个黑色圆形
    # draw.ellipse((50, 50, 250, 250))

    # 保存图片
    image.save(f"{config.imageCacheDirectory}/game_image.png")


def placingPieces(index, userId):
    gameData = playerGameDataMap[userId]
    playerList = gameData["playerList"]
    map = gameData["map"]
    positonIJ = fromIndexToIJ(index)
    i = positonIJ[0]
    j = positonIJ[1]
    if map[i][j]["status"] == 0:
        map[i][j]["status"] = 2
        playerList.append(index)
        return True
    else:
        return False


def deleteFilesStartswith(directory, prefix):
    # 列出目录中的所有文件
    files = os.listdir(directory)

    # 删除以指定字符串开头的文件
    for file in files:
        if file.startswith(prefix):
            os.remove(os.path.join(directory, file))


def textToNumber(text):
    try:
        number = int(text)
        return number
    except ValueError:
        return None


def textInNumber(text, minNumber, maxNumber):
    try:
        return minNumber <= int(text) <= maxNumber
    except ValueError:
        return False


async def userInGame(event: Event) -> bool:
    return (
        textInNumber(event.get_plaintext(), 1, 81)
        and event.get_user_id() in playerGameDataMap
    )


downloadImageToDirectory(
    "https://marketplace.canva.cn/PX2nY/MAA9p7PX2nY/4/tl/canva-user--MAA9p7PX2nY.png",
    f"{config.imageCacheDirectory}/common_user.png",
)
deleteFilesStartswith(config.imageCacheDirectory, "in_game_")
checkAndAddToCache()
# 创建后台线程
background_thread = threading.Thread(target=downloadPicture)
background_thread.daemon = True  # 将线程设置为守护线程，使程序退出时自动结束
background_thread.start()

drawPicture(f"{config.imageCacheDirectory}/common_user.png")

surroundTheCat = on_command("围猫咪", priority=10)
surroundStep = on_regex(r"\d\d?", rule=userInGame, priority=60)


@driver.on_shutdown
async def shutdown():
    global running
    running = False
    with condition:
        condition.notify_all()


@surroundTheCat.handle()
async def handle_function(event: Event, state: T_State):
    gameData = initGame()
    userId = event.get_user_id()
    if userId in playerGameDataMap:
        with condition:
            recyclingGameData(playerGameDataMap.pop(userId))
    playerGameDataMap[userId] = gameData
    drawGameData(gameData, f"{config.imageCacheDirectory}/common_user.png")
    await surroundTheCat.finish("游戏开始")


# 通过依赖注入或事件处理函数来进行业务逻辑处理


# 处理控制台回复
@surroundTheCat.handle()
async def handle_console_reply(bot: ConsoleBot, state: T_State):
    key = "console"
    if key in playerGameDataMap:
        with condition:
            recyclingGameData(playerGameDataMap.pop(key))
    playerGameDataMap[key] = state["gameData"]
    drawGameData(state["gameData"], f"{config.imageCacheDirectory}/common_user.png")
    await surroundTheCat.finish("游戏开始")


# 处理 OneBot 私聊回复
@surroundTheCat.handle()
async def handle_onebot_private_reply(
    bot: OnebotBot, event: PrivateMessageEvent, state: T_State
):
    key = f"private-{event.user_id}"
    if key in playerGameDataMap:
        with condition:
            recyclingGameData(playerGameDataMap.pop(key))

    playerGameDataMap[key] = state["gameData"]
    await surroundTheCat.finish("游戏开始")


# 处理 OneBot 群聊回复
@surroundTheCat.handle()
async def handle_onebot_group_reply(
    bot: OnebotBot, event: GroupMessageEvent, state: T_State
):
    key = f"group-{event.group_id}"
    if key in playerGameDataMap:
        with condition:
            recyclingGameData(playerGameDataMap.pop(key))
    playerGameDataMap[key] = state["gameData"]
    await surroundTheCat.finish("游戏开始")


@surroundStep.handle()
async def handleGameNextStep(event: Event, state: T_State):
    placingPiecesNumber = textToNumber(event.get_plaintext())
    userId = event.get_user_id()
    if 1 <= placingPiecesNumber <= 81 and userId in playerGameDataMap:
        result = placingPieces(placingPiecesNumber, userId)
        if result:
            moveAllCat(playerGameDataMap[userId])
        drawGameData(
            playerGameDataMap[userId], f"{config.imageCacheDirectory}/common_user.png"
        )
        if result:
            await surroundStep.finish("下子完成")
        else:
            await surroundStep.finish("无效位置")
    await surroundStep.finish("不在游戏中")


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
