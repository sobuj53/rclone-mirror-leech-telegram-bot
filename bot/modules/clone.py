from argparse import ArgumentParser
from asyncio import sleep
from random import SystemRandom
from string import ascii_letters, digits
from bot.helper.ext_utils.human_format import get_readable_file_size
from bot.helper.mirror_leech_utils.gd_utils.clone import gdClone
from bot.helper.mirror_leech_utils.gd_utils.count import gdCount
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from bot import bot, LOGGER, status_dict, status_dict_lock, config_dict
from bot.helper.mirror_leech_utils.download_utils import direct_link_generator
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.ext_utils.help_messages import CLONE_HELP_MESSAGE
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import (
    is_gdrive_id,
    is_gdrive_link,
    is_share_link,
    new_task,
    run_sync_to_async,
)
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    deleteMessage,
    sendMessage,
    sendStatusMessage,
)
from bot.helper.mirror_leech_utils.status_utils.clone_status import CloneStatus
from bot.modules.tasks_listener import TaskListener


async def clone(client, message):
    message_list = message.text.split()
    user = message.from_user or message.sender_chat

    try:
        args = parser.parse_args(message_list[1:])
    except Exception:
        await sendMessage(CLONE_HELP_MESSAGE, message)
        return

    multi = args.multi
    link = " ".join(args.link)

    if username := user.username:
        tag = f"@{username}"
    else:
        tag = message.from_user.mention

    if not link and (reply_to := message.reply_to_message):
        link = reply_to.text.split("\n", 1)[0].strip()

    @new_task
    async def __run_multi():
        if multi > 1:
            await sleep(5)
            msg = [s.strip() for s in message_list]
            index = msg.index("-i")
            msg[index + 1] = f"{multi - 1}"
            nextmsg = await client.get_messages(
                chat_id=message.chat.id, message_ids=message.reply_to_message_id + 1
            )
            nextmsg = await sendMessage(" ".join(msg), nextmsg)
            nextmsg = await client.get_messages(
                chat_id=message.chat.id, message_ids=nextmsg.id
            )
            nextmsg.from_user = message.from_user
            await sleep(5)
            await clone(client, nextmsg)

    __run_multi()

    if not link:
        await sendMessage(CLONE_HELP_MESSAGE, message)
        return

    if is_share_link(link):
        try:
            link = await run_sync_to_async(direct_link_generator, link)
            LOGGER.info(f"Generated link: {link}")
        except DirectDownloadLinkException as e:
            LOGGER.error(str(e))
            if str(e).startswith("ERROR:"):
                await sendMessage(str(e), message)
                return

    if is_gdrive_link(link) or is_gdrive_id(link):
        name, mime_type, size, files, _ = await run_sync_to_async(
            gdCount().count, link, user.id
        )
        if mime_type is None:
            await sendMessage(name, message)
            return
        user_id = message.from_user.id
        listener = TaskListener(message, tag, user_id)
        drive = gdClone(link, listener)
        if files <= 20:
            msg = await sendMessage(f"Cloning: <code>{link}</code>", message)
        else:
            msg = ""
            gid = "".join(SystemRandom().choices(ascii_letters + digits, k=12))
            async with status_dict_lock:
                status_dict[message.id] = CloneStatus(drive, size, message, gid)
            await sendStatusMessage(message)
        link, size, mime_type, files, folders, dir_id = await run_sync_to_async(
            drive.clone
        )
        if msg:
            await deleteMessage(msg)
        if not link:
            return
        if not config_dict["NO_TASKS_LOGS"]:
            LOGGER.info(f"Cloning Done: {name}")
        size = get_readable_file_size(size)
        await listener.onUploadComplete(
            link, size, files, folders, mime_type, name, is_gdrive=True, dir_id=dir_id
        )
    else:
        await sendMessage(CLONE_HELP_MESSAGE, message)


parser = ArgumentParser(description="Clone args usage:")
parser.add_argument("link", nargs="*", default="")
parser.add_argument("-i", nargs="?", default=0, dest="multi", type=int)

bot.add_handler(
    MessageHandler(
        clone,
        filters=filters.command(BotCommands.CloneCommand)
        & (CustomFilters.user_filter | CustomFilters.chat_filter),
    )
)
