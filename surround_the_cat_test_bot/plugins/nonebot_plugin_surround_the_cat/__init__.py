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
import urllib.request
import zipfile
from tqdm import tqdm
from collections import deque
import networkx as nx
import random
import inspect
import signal
from PIL import Image, ImageDraw, ImageFont
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

fontPath = ""

os.makedirs(config.imageCacheDirectory, exist_ok=True)


# 递归搜索函数
def searchFiles(directory, extension):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(extension):
                return os.path.join(root, file)  # 如果找到一个文件就返回True
    return ""  # 如果遍历完所有文件都没找到匹配的就返回False


# 下载文件并显示下载进度和速度
def downloadWithProgress(url, savePath):
    logger.debug("开始下载...")
    try:
        ## 设置代理服务器地址和端口号
        # proxyAddress = "127.0.0.1:8888"
        #
        ## 创建代理处理程序
        # proxyHandler = urllib.request.ProxyHandler({'http': proxyAddress, 'https': proxyAddress})
        #
        ## 创建URL打开器（opener）
        # opener = urllib.request.build_opener(proxyHandler)
        #
        ## 安装URL打开器为全局默认
        # urllib.request.install_opener(opener)

        # 创建一个Request对象，并设置自定义的HTTP头
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "NoneBot/surroundTheCatTestBot")
        with urllib.request.urlopen(req) as response, open(savePath, "wb") as outFile:
            # 获取文件大小
            file_size = int(response.info().get("Content-Length", -1))

            # 初始化进度条
            progressBar = tqdm(
                total=file_size,
                unit="B",
                unit_scale=True,
                desc=os.path.basename(savePath),
                ncols=100,
            )

            # 下载文件并显示进度
            downloaded = 0
            blockSize = 1024 * 8
            while True:
                buffer = response.read(blockSize)
                if not buffer:
                    break
                downloaded += len(buffer)
                progressBar.update(len(buffer))
                outFile.write(buffer)

            progressBar.close()
            logger.debug("下载完成.")
            return True
    except Exception as e:
        logger.error("异常:", e)
    return False


# 解压缩zip文件
def extractZip(zip_file, extract_dir):
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        logger.debug("开始解压缩...")
        zip_ref.extractall(extract_dir)
        logger.debug("解压缩完成.")


# 下载并解压缩zip文件
def downloadAndExtract(url, savePath, extractDir):
    if downloadWithProgress(url, savePath):
        extractZip(savePath, extractDir)


def checkFontExits():
    global fontPath
    if os.path.exists("C:/Windows/Fonts/msyh.ttc"):
        fontPath = "C:/Windows/Fonts/msyh.ttc"
    while fontPath == "":
        fontPath = searchFiles(config.imageCacheDirectory, ".ttf")
        if fontPath == "":
            logger.info(
                f"缺少字体文件，请将字体文件放在{config.imageCacheDirectory}目录下，后缀要求为.ttf"
            )
            # 得意黑字体
            # https://github.com/atelier-anchor/smiley-sans
            downloadAndExtract(
                "https://atelier-anchor.com/downloads/smiley-sans-v2.0.1.zip",
                f"{config.imageCacheDirectory}/archive.zip",
                f"{config.imageCacheDirectory}",
            )


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
            try:
                downloadImage(json_data["data"][0]["urls"]["original"])
            except Exception as e:
                pass


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
    inventory = {"roadbreaker": 3, "felineLure": 3, "frostWall": 3}
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
        "inventory": inventory,
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


def distanceBetweenIndex(firstIndex, secondIndex):
    if firstIndex < secondIndex:
        topI, topJ = fromIndexToIJ(firstIndex)
        bottomI, bottomJ = fromIndexToIJ(secondIndex)
    else:
        topI, topJ = fromIndexToIJ(secondIndex)
        bottomI, bottomJ = fromIndexToIJ(firstIndex)
    distance = bottomJ - topJ
    if bottomI > topI:
        left = bottomI - distance // 2
        if left <= topI:
            return distance
        if distance % 2 == 1 and bottomJ % 2 == 1:
            left = left - 1
        return distance + left - topI
    else:
        left = bottomI + distance // 2
        if left >= topI:
            return distance
        if distance % 2 == 1 and bottomJ % 2 == 0:
            left = left + 1
        return distance - left + topI


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


def bfsShortestPathToTarget(gameData, startNode, endNode):
    # 使用广度优先搜索算法找到从起点到所有出口的最短路径
    shortestPaths = nx.shortest_path(
        createGraphFromGamedata(gameData), source=startNode
    )
    shortestPaths = {
        key: value for key, value in shortestPaths.items() if len(value) > 1
    }
    if len(shortestPaths) == 0:
        return startNode
    # 找到最短路径中最短的那条路径
    shortest_exit = min(shortestPaths, key=lambda x: distanceBetweenIndex(x, endNode))

    return shortestPaths[shortest_exit][1]


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


def moveAllCatToTarget(gameData, targetIndex):
    map = gameData["map"]
    catList = gameData["catList"]
    for cat in catList:
        if cat["status"] == 0:
            catI = cat["i"]
            catJ = cat["j"]
            map[catI][catJ]["status"] = 0
            catAlgorithm = cat["algorithm"]
            if catAlgorithm == 1:
                nowIndex = fromIJToIndex(catI, catJ)
                nextIndex = bfsShortestPathToTarget(gameData, nowIndex, targetIndex)
                if nowIndex != nextIndex:
                    i, j = fromIndexToIJ(nextIndex)
                    cat["i"] = i
                    cat["j"] = j
                    if nextIndex in exitList:
                        cat["status"] = -1
                    else:
                        map[i][j]["status"] = 3
                else:
                    cat["status"] = 1


def drawGameData(gameData, userImage):
    map = gameData["map"]
    catList = gameData["catList"]
    playerList = gameData["playerList"]
    inventory = gameData["inventory"]
    gameMapImageWidth = 500
    gameMapImageHeight = 418
    # 创建一个 300x300 的白色图片
    image = Image.new(
        "RGB", (gameMapImageWidth, gameMapImageHeight + 180), (179, 217, 254)
    )

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
    font = ImageFont.truetype(fontPath, 15)
    drawLeft = 15
    drawTop = gameMapImageHeight + 5
    lineheight = 20
    draw.text(
        (drawLeft, drawTop),
        f"围猫咪：猫咪无法到达边缘视为被抓住，猫咪到达边缘视为逃跑成功",
        fill="black",
        font=font,
    )
    drawTop = drawTop + lineheight
    draw.text(
        (drawLeft, drawTop),
        f"　　　　以抓住所有猫咪为目标开始游戏吧",
        fill="black",
        font=font,
    )
    drawTop = drawTop + lineheight
    draw.text(
        (drawLeft, drawTop),
        f"数　字：输入1-81增加障碍物",
        fill="black",
        font=font,
    )
    drawTop = drawTop + lineheight
    draw.text(
        (drawLeft, drawTop),
        f"炸数字：将指定格以及周围的格子炸掉（剩余：{inventory['roadbreaker']}）",
        fill="black",
        font=font,
    )
    drawTop = drawTop + lineheight
    draw.text(
        (drawLeft, drawTop),
        f"诱数字：只能指定猫咪周围的格子，在指定格放置猫条（剩余：{inventory['felineLure']}）",
        fill="black",
        font=font,
    )
    drawTop = drawTop + lineheight
    draw.text(
        (drawLeft, drawTop),
        f"　　　　吸引所有猫咪向这里前进一格，猫条会立即被猫咪吃掉",
        fill="black",
        font=font,
    )
    drawTop = drawTop + lineheight
    draw.text(
        (drawLeft, drawTop),
        f"冰数字：与间隔一格的障碍物相连，在间隔的一格里建立冰墙（剩余：{inventory['frostWall']}）",
        fill="black",
        font=font,
    )
    # 绘制一个黑色圆形
    # draw.ellipse((50, 50, 250, 250))

    # 保存图片
    image.save(f"{config.imageCacheDirectory}/game_image.png")


def checkGameFinish(gameData):
    catList = gameData["catList"]
    for cat in catList:
        if cat["status"] == 0:
            return False
    return True


def aroundFromIJ(i, j):
    aroundList = []
    if j % 2 == 0:
        if i - 1 > 0:
            aroundList.append((i - 1, j))
        if j - 1 > 0:
            aroundList.append((i, j - 1))
        if j + 1 <= mapHeight:
            aroundList.append((i, j + 1))
        if i + 1 <= mapWidth:
            aroundList.append((i + 1, j))
            if j - 1 > 0:
                aroundList.append((i + 1, j - 1))
            if j + 1 <= mapHeight:
                aroundList.append((i + 1, j + 1))
    else:
        if i - 1 > 0:
            aroundList.append((i - 1, j))
            if j - 1 > 0:
                aroundList.append((i - 1, j - 1))
            if j + 1 <= mapHeight:
                aroundList.append((i - 1, j + 1))
        if i + 1 <= mapWidth:
            aroundList.append((i + 1, j))
        if j - 1 > 0:
            aroundList.append((i, j - 1))
        if j + 1 <= mapHeight:
            aroundList.append((i, j + 1))
    return aroundList


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


def useRoadbreaker(index, userId):
    gameData = playerGameDataMap[userId]
    playerList = gameData["playerList"]
    map = gameData["map"]
    catList = gameData["catList"]
    inventory = gameData["inventory"]
    if inventory["roadbreaker"] == 0:
        return False
    positonIJ = fromIndexToIJ(index)
    i = positonIJ[0]
    j = positonIJ[1]
    if map[i][j]["status"] == 0:
        map[i][j]["status"] = 2
        inventory["roadbreaker"] = inventory["roadbreaker"] - 1
        playerList.append(index)
        aroundList = aroundFromIJ(i, j)
        for around in aroundList:
            aroundI = around[0]
            aroundJ = around[1]
            if map[aroundI][aroundJ]["status"] == 0:
                map[aroundI][aroundJ]["status"] = 2
                playerList.append(fromIJToIndex(aroundI, aroundJ))
            if map[aroundI][aroundJ]["status"] == 3:
                for cat in catList:
                    if cat["status"] == 0:
                        if cat["i"] == aroundI and cat["j"] == aroundJ:
                            cat["status"] = -2
                            break
                map[aroundI][aroundJ]["status"] = 2
                playerList.append(fromIJToIndex(aroundI, aroundJ))
        return True
    else:
        return False


def useFelineLure(index, userId):
    gameData = playerGameDataMap[userId]
    map = gameData["map"]
    catList = gameData["catList"]
    inventory = gameData["inventory"]
    if inventory["felineLure"] == 0:
        return False
    positonIJ = fromIndexToIJ(index)
    i = positonIJ[0]
    j = positonIJ[1]
    if map[i][j]["status"] == 0:
        aroundList = aroundFromIJ(i, j)
        nearbyCat = False
        for around in aroundList:
            aroundI = around[0]
            aroundJ = around[1]
            for cat in catList:
                if cat["status"] == 0:
                    if cat["i"] == aroundI and cat["j"] == aroundJ:
                        nearbyCat = True
                        break
            if nearbyCat:
                moveAllCatToTarget(gameData, index)
                inventory["felineLure"] = inventory["felineLure"] - 1
                return True
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
    message = event.get_plaintext()
    if message.startswith("炸"):
        message = message.replace("炸", "", 1)
    elif message.startswith("诱"):
        message = message.replace("诱", "", 1)
    elif message.startswith("冰"):
        message = message.replace("冰", "", 1)
    return textInNumber(message, 1, 81) and event.get_user_id() in playerGameDataMap


checkFontExits()
if not os.path.exists(f"{config.imageCacheDirectory}/common_user.png"):
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
surroundStep = on_regex(r"^\d\d?$", rule=userInGame, priority=60)
roadbreakerMatcher = on_regex(r"^炸\d\d?$", rule=userInGame, priority=60)
felineLureMatcher = on_regex(r"^诱\d\d?$", rule=userInGame, priority=60)
frostWallMatcher = on_regex(r"^冰\d\d?$", rule=userInGame, priority=60)


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
        if checkGameFinish(playerGameDataMap[userId]):
            await surroundTheCat.finish("游戏结束")
        else:
            if result:
                await surroundStep.finish("下子完成")
            else:
                await surroundStep.finish("无效位置")
    await surroundStep.finish("不在游戏中")


@roadbreakerMatcher.handle()
async def handleUseRoadbreaker(event: Event, state: T_State):
    message = event.get_plaintext()
    message = message.replace("炸", "", 1)
    placingPiecesNumber = textToNumber(message)
    userId = event.get_user_id()
    if 1 <= placingPiecesNumber <= 81 and userId in playerGameDataMap:
        result = useRoadbreaker(placingPiecesNumber, userId)
        if result:
            moveAllCat(playerGameDataMap[userId])
        drawGameData(
            playerGameDataMap[userId], f"{config.imageCacheDirectory}/common_user.png"
        )
        if checkGameFinish(playerGameDataMap[userId]):
            await roadbreakerMatcher.finish("游戏结束")
        else:
            if result:
                await roadbreakerMatcher.finish("使用炸弹成功")
            else:
                await roadbreakerMatcher.finish("炸弹不足或无效位置")
    await roadbreakerMatcher.finish("不在游戏中")


@felineLureMatcher.handle()
async def handleUseFelineLure(event: Event, state: T_State):
    message = event.get_plaintext()
    message = message.replace("诱", "", 1)
    placingPiecesNumber = textToNumber(message)
    userId = event.get_user_id()
    if 1 <= placingPiecesNumber <= 81 and userId in playerGameDataMap:
        result = useFelineLure(placingPiecesNumber, userId)
        drawGameData(
            playerGameDataMap[userId], f"{config.imageCacheDirectory}/common_user.png"
        )
        if checkGameFinish(playerGameDataMap[userId]):
            await felineLureMatcher.finish("游戏结束")
        else:
            if result:
                await felineLureMatcher.finish("已放置猫条吸引猫咪")
            else:
                await felineLureMatcher.finish("猫条不足或无效位置")
    await felineLureMatcher.finish("不在游戏中")


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
