intents = discord.Intents.all()
intents.members = True
intents.messages = True

client = commands.Bot(command_prefix='+', intents=intents)

conn = sqlite3.connect('economy.db')
cursor = conn.cursor()
conn.commit()

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0
                )''')

cursor.execute('''CREATE TABLE IF NOT EXISTS shop (
                    item_id INTEGER PRIMARY KEY,
                    item_name TEXT,
                    uuid TEXT,
                    price INTEGER
                )''')

cursor.execute('''CREATE TABLE IF NOT EXISTS user_items (
                    user_id INTEGER,
                    item_id INTEGER,
                    quantity INTEGER,
                    PRIMARY KEY (user_id, item_id)
                )''')

purchase_channel_id = None

@client.command()
@commands.has_permissions(administrator=True)
async def set_purchase_channel(ctx, channel: discord.TextChannel):
    global purchase_channel_id
    purchase_channel_id = channel.id
    await ctx.send(f'Канал для сообщений о покупках успешно установлен: {channel.mention}')

def get_balance(user_id):
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def update_balance(user_id, amount):
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()

def add_item_to_shop(item_name, uuid, price):
    cursor.execute('INSERT INTO shop (item_name, uuid, price) VALUES (?, ?, ?)', (item_name, uuid, price))
    conn.commit()

def remove_item_from_shop(item_id):
    cursor.execute('DELETE FROM shop WHERE item_id = ?', (item_id,))
    conn.commit()

def get_shop_items():
    cursor.execute('SELECT item_id, item_name, uuid, price FROM shop')
    return cursor.fetchall()

def get_item_by_id(item_id):
    cursor.execute('SELECT item_name, price FROM shop WHERE item_id = ?', (item_id,))
    return cursor.fetchone()

needed_role_id = None

@client.command()
@commands.has_permissions(manage_roles=True)
async def set_needed_role(ctx, role: discord.Role):
    global needed_role_id
    needed_role_id = role.id
    await ctx.send(f'Роль Ивентолога успешно установлена: {role.mention}')

def has_required_role():
    async def predicate(ctx):
        if needed_role_id is None:
            await ctx.send('Роль Ивентолога не установлена. Обратитесь к администратору сервера.')
            return False

        if needed_role_id in [role.id for role in ctx.author.roles]:
            return True
        else:
            await ctx.send(f'У вас недостаточно прав для использования команды {ctx.command.name}')
            return False
    return commands.check(predicate)

@client.command()
@has_required_role()
async def bal(ctx):
    user_id = ctx.author.id
    balance = get_balance(user_id)
    await ctx.send(f'{ctx.author.mention}, ваш текущий баланс: {balance} баллов')

@client.command()
@has_required_role()
@commands.has_permissions(administrator=True)
async def addshop(ctx, item_name: str, uuid: str, price: int):
    add_item_to_shop(item_name, uuid, price)
    await ctx.send(f'Предмет "{item_name}" с UUID "{uuid}" успешно добавлен в магазин за {price} баллов')

@client.command()
@has_required_role()
@commands.has_permissions(administrator=True)
async def removeshop(ctx, item_number: int):
    item = get_item_by_id(item_number)
    if item:
        remove_item_from_shop(item_number)
        await ctx.send(f'Предмет "{item[0]}" успешно удален из магазина')
    else:
        await ctx.send('Предмет с указанным номером не найден в магазине')

@client.command()
@has_required_role()
@commands.has_permissions(administrator=True)
async def givemoney(ctx, user: discord.Member, amount: int):
    update_balance(user.id, amount)
    await ctx.send(f'{amount} баллов успешно выдано пользователю {user.mention}')

@client.command()
@has_required_role()
async def shop(ctx):
    shop_items = get_shop_items()
    if len(shop_items) == 0:
        await ctx.send('Магазин пуст')
        return

    shop_list = '\n'.join([f'({item[0]}.) {item[1]} - {item[2]} баллов' for item in shop_items])
    await ctx.send(f'Предметы в магазине:\n{shop_list}\n\nДля покупки используйте команду !buy <номер>')

@client.command()
async def buy(ctx, item_number: int):
    if purchase_channel_id is None:
        await ctx.send('Канал для сообщений о покупках не установлен. Обратитесь к администратору сервера.')
        return

    user_id = ctx.author.id
    item = get_item_by_id(item_number)
    if item:
        item_id, price = item
        if get_balance(user_id) >= price:
            update_balance(user_id, -price)
            item_id = str(uuid.uuid4())

            cursor.execute('SELECT quantity FROM user_items WHERE user_id = ? AND item_id = ?', (user_id, item_number))
            result = cursor.fetchone()
            if result:
                current_quantity = result[0]
                new_quantity = current_quantity + 1
                cursor.execute('UPDATE user_items SET quantity = ? WHERE user_id = ? AND item_id = ?', (new_quantity, user_id, item_number))
            else:
                cursor.execute('INSERT INTO user_items (user_id, item_id, item_number, quantity) VALUES (?, ?, ?, ?)', (user_id, item_id, item_number, 1))

            conn.commit()

            await ctx.send(f'{ctx.author.mention}, вы успешно приобрели предмет')
            purchase_channel = client.get_channel(purchase_channel_id)
            if purchase_channel:
                await purchase_channel.send(f'{ctx.author.mention} купил предмет {item_info[1]}')

        else:
            await ctx.send(f'{ctx.author.mention}, у вас недостаточно монет для покупки этого предмета')
    else:
        await ctx.send('Предмет с указанным номером не найден в магазине')

def get_item_info(item_id):
    cursor.execute('SELECT item_name FROM shop WHERE item_id = ?', (item_id,))
    result = cursor.fetchone()
    return result[0] if result else 'Предмет не найден'

@client.command()
@has_required_role()
async def myitems(ctx):
    user_id = ctx.author.id
    cursor.execute('SELECT item_id, item_number, quantity FROM user_items WHERE user_id = ?', (user_id,))
    items = cursor.fetchall()

    if not items:
        await ctx.send('У вас пока нет приобретенных предметов')
        return

    items_list = '\n'.join([f'{item[1]} (ID: {item[0]}) - Количество: {item[2]}' for item in items])

    await ctx.send(f'{ctx.author.mention}, у вас есть следующие приобретенные предметы:\n{items_list}')

@client.command()
@has_required_role()
@commands.has_permissions(administrator=True)
async def removeitems(ctx, user: discord.Member, item_id: str, quantity: int):
    user_id = user.id

    cursor.execute('SELECT quantity FROM user_items WHERE user_id = ? AND item_id = ?', (user_id, item_id))
    result = cursor.fetchone()

    if not result:
        await ctx.send(f'{user.mention} не имеет предмета с указанным ID')
        return

    current_quantity = result[0]
    if current_quantity >= quantity:
        new_quantity = current_quantity - quantity
        if new_quantity > 0:
            cursor.execute('UPDATE user_items SET quantity = ? WHERE user_id = ? AND item_id = ?', (new_quantity, user_id, item_id))
        else:
            cursor.execute('DELETE FROM user_items WHERE user_id = ? AND item_id = ?', (user_id, item_id))
        conn.commit()
        await ctx.send(f'{quantity} предметов было удалено у {user.mention}')
    else:
        await ctx.send(f'{user.mention} не имеет достаточного количества предметов')

@client.command()
@has_required_role()
async def view_inventory(ctx, member: discord.Member):
    user_id = member.id
    cursor.execute('SELECT item_id, uuid, quantity FROM user_items WHERE user_id = ?', (user_id,))
    items = cursor.fetchall()

    if not items:
        await ctx.send('У пользователя пока нет приобретенных предметов')
        return

    shop_items = get_shop_items()
    user_items_info = [(item[1], item[2]) for item in items if item[0] in [i[0] for i in shop_items]]

    items_list = '\n'.join([f'{item_info[0]} (ID: {item_info[0]}) - Количество: {item_info[1]}' for item_info in user_items_info])

    await ctx.send(f'{member.mention}, у пользователя есть следующие приобретенные предметы:\n{items_list}')

@client.command()
@has_required_role()
@commands.has_permissions(administrator=True)
async def takemoney(ctx, user: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send('Сумма для забирания должна быть положительным числом')
        return

    user_id = user.id
    user_balance = get_balance(user_id)

    if user_balance < amount:
        current_balance = get_user_balance(user_id)
        await ctx.send(f'У пользователя {user.mention} недостаточно баллов для забирания этой суммы. У него {current_balance} баллов')
        return

    update_balance(user_id, -amount)
    await ctx.send(f'У пользователя {user.mention} успешно забрано {amount} баллов')

payments = {}

@client.command()
@has_required_role()
@commands.has_permissions(administrator=True)
async def set_payment(ctx, blackwood: int, minori: int, rockberry: int):
    global payments
    payments = {'Blackwood': blackwood, 'Minori': minori, 'Rockberry': rockberry}
    await ctx.send(f'Настройки выплат успешно обновлены:\n'
                   f'Blackwood: {blackwood} баллов\n'
                   f'Minori: {minori} баллов\n'
                   f'Rockberry: {rockberry} баллов')

@client.command()
@commands.cooldown(1, 14400, commands.BucketType.user)
async def claim(ctx, payment_type: str):
    global payments
    if payment_type in payments:
        amount = payments[payment_type]
        update_balance(ctx.author.id, amount)
        await ctx.send(f'{ctx.author.mention}, вы успешно получили {amount} баллов за {payment_type}')
    else:
        available_payment_types = ', '.join(payments.keys())
        await ctx.send(f'{ctx.author.mention}, указанный тип выплаты не существует. Доступные типы: {available_payment_types}')

client.run('MTEzNzUwMjM3MTMwODYzODMxMA.GS8Ycm.ISDI-RiMhp3uUTiQG655T9N7v4Lu-jchqSwpyI')
