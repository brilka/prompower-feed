# ==============================================================================
# НАЗНАЧЕНИЕ СКРИПТА (ОПИСАНИЕ ДЛЯ НОВИЧКОВ):
#
# Этот скрипт автоматически собирает информацию о товарах с сайта Prompower.ru 
# и формирует специальный файл формата XML (feed.xml) для площадки Industrial.Market.
#
# Что именно делает скрипт:
# 1. Проверяет, не поставлен ли запуск на паузу до определенной даты.
# 2. Подключается к API Prompower и скачивает список категорий товаров.
# 3. Скачивает существующий XML-файл с prompower.ru, чтобы забрать оттуда 
#    самые точные ссылки на картинки товаров.
# 4. Делает запросы к API для получения списка всех товаров Prompower и UniMAT.
# 5. Фильтрует товары (отсеивает позиции с нулевой или отсутствующей ценой).
# 6. Упаковывает все данные в единый файл feed.xml и сохраняет его на GitHub.
# ==============================================================================

# ------------------------------------------------------------------------------
# ПОДКЛЮЧЕНИЕ БИБЛИОТЕК (ИМПОРТ)
# Библиотеки — это готовые наборы инструментов, которые расширяют возможности Python.
# ------------------------------------------------------------------------------
import os        # Работа с системой (нужен для получения секретных ключей API из настроек GitHub)
import json      # Работа с форматом JSON (в этом формате API возвращает нам данные о товарах)
import requests  # Работа с интернетом (отправка запросов на сайт prompower.ru для получения данных)
import xml.etree.ElementTree as ET  # Создание и сборка XML-структуры будущего файла
from xml.dom import minidom          # Красивое форматирование XML-файла (добавление отступов и переносов строк)
from datetime import datetime        # Работа с датой и временем (нужно для проверки паузы и записи даты в файл)


# ==============================================================================
# 1. НАСТРОЙКА ПАУЗЫ ОБНОВЛЕНИЯ
# ==============================================================================
# Здесь вы можете поставить автообновление на паузу до конкретной даты.
# Формат записи: "ГГГГ-ММ-ДД" (Год-Месяц-День).
# Если указать "2026-09-01", то до 1 сентября 2026 года скрипт запускаться будет, 
# но сразу завершит работу, не меняя файл feed.xml.
# Если вы хотите, чтобы фид обновлялся прямо сейчас — оставьте пустые кавычки: ""
PAUSE_UNTIL_DATE = "2026-08-19"


# ==============================================================================
# 2. ОСНОВНЫЕ НАСТРОЙКИ И АДРЕСА (КОНФИГУРАЦИЯ)
# ==============================================================================
# Получаем логин (email) и ключ API из защищенных секретов GitHub Secrets.
# Окружение (os.environ) позволяет не писать пароли открытым текстом прямо в коде.
API_EMAIL = os.environ.get('API_EMAIL')
API_KEY = os.environ.get('API_KEY')

# Базовый веб-адрес, к которому мы будем обращаться для работы с API
BASE_URL = "https://prompower.ru/api"

# Ссылка на сторонний XML-файл Prompower, откуда мы берем качественные ссылки на картинки
EXTERNAL_FEED_URL = "https://prompower.ru/feed.xml"

# Список адресов API для получения товаров разных брендов.
# Мы создаем словарь, где ключ — имя бренда, а значение — адрес метода API.
PRODUCTS_API = {
    "Prompower": f"{BASE_URL}/prod/getProducts",
    "Unimat": f"{BASE_URL}/prod/getUnimatProducts"
}

# Адрес метода API для получения списка категорий товаров
CATEGORIES_API_URL = f"{BASE_URL}/categories"


# ==============================================================================
# 3. ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: ЗАПРОС К API PROMPOWER
# ==============================================================================
def fetch_data(url, is_post=False, payload=None):
    """
    Эта функция отправляет сетевой запрос к сайту prompower.ru и возвращает ответ.
    
    Параметры:
    - url: веб-адрес, к которому обращаемся.
    - is_post: если True (Истина) — отправляем POST-запрос с логином и ключом (нужно для товаров).
               если False (Ложь) — отправляем простой GET-запрос (нужно для категорий).
    - payload: дополнительные данные для запроса (если есть).
    """
    # Указываем серверу, что мы хотим общаться с ним в формате JSON
    headers = {"Content-Type": "application/json"}
    
    # Если это POST-запрос, добавляем обязательные данные для авторизации
    if is_post:
        # Проверяем, заполнил ли пользователь секреты в GitHub
        if not API_EMAIL or not API_KEY:
            print("Ошибка: Секреты API_EMAIL или API_KEY не найдены в настройках GitHub!")
            return None
        
        # Формируем словарь с данными авторизции
        post_payload = {
            "email": API_EMAIL,
            "key": API_KEY,
            "format": "json" # Просим вернуть ответ именно в формате JSON
        }
        # Если передали дополнительные параметры — объединяем их
        if payload:
            post_payload.update(payload)
            
        try:
            # Отправляем POST-запрос на сервер
            response = requests.post(url, headers=headers, data=json.dumps(post_payload))
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при выполнении POST-запроса к {url}: {e}")
            return None
    else:
        # Если это простой GET-запрос (для категорий)
        try:
            response = requests.get(url, headers=headers)
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при выполнении GET-запроса к {url}: {e}")
            return None

    # Проверяем ответ от сервера
    try:
        response.raise_for_status() # Вызовет ошибку, если сервер ответил "404 Not Found" или "500 Server Error"
        return response.json()      # Превращаем текстовый ответ сервера в удобный объект Python
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Ошибка при получении данных от {url}: {e}")
        print(f"Ответ сервера: {response.text}")
        return None
    except json.JSONDecodeError:
        print(f"Ошибка декодирования JSON для {url}. Ответ сервера не в формате JSON.")
        return None


# ==============================================================================
# 4. ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: СБОР ССЫЛОК НА КАРТИНКИ
# ==============================================================================
def fetch_external_images_map():
    """
    Скачивает существующий XML-файл с prompower.ru/feed.xml,
    находит там ссылки на картинки и создает "картотеку" вида:
    {"Артикул_Товара": "https://ссылка_на_картинку.jpg"}
    """
    print(f"Загрузка внешнего XML для получения картинок с {EXTERNAL_FEED_URL}...")
    try:
        # Скачиваем XML-файл с сайта
        response = requests.get(EXTERNAL_FEED_URL)
        response.raise_for_status()
        
        # Разбираем структуру XML с помощью библиотеки ElementTree
        root = ET.fromstring(response.content)
        
        images_map = {} # Создаем пустой словарь для хранения пар Артикул -> Ссылка
        
        # Проходим по всем элементам <offer> в скачанном файле
        for offer in root.findall(".//offer"):
            offer_id = offer.get("id")         # Получаем значение атрибута id="..." (это артикул)
            picture_tag = offer.find("picture") # Находим внутри тег <picture>
            
            # Если артикул есть и тег с картинкой не пустой
            if offer_id and picture_tag is not None and picture_tag.text:
                # Запоминаем: по этому артикулу лежит эта ссылка на картинку
                images_map[offer_id] = picture_tag.text.strip()
                
        print(f"Успешно загружено картинок для {len(images_map)} товаров из внешнего XML.")
        return images_map

    except Exception as e:
        # Если что-то пошло не так (например, сайт недоступен), пишем предупреждение
        # и возвращаем пустой словарь, чтобы скрипт не упал с ошибкой.
        print(f"Внимание: Не удалось загрузить картинки из внешнего XML ({e}). Скрипт продолжит работу без них.")
        return {}


# ==============================================================================
# 5. ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: ЗАГРУЗКА ВСЕХ ТОВАРОВ (PROMPOWER + UNIMAT)
# ==============================================================================
def fetch_all_products():
    """
    Опрашивает API Prompower для каждого бренда (Prompower и UniMAT),
    объединяет их товары в один общий список и помечает бренд для каждого товара.
    """
    all_products = [] # Общий массив для всех товаров
    
    # Цикл по нашему словарю PRODUCTS_API (сначала Prompower, потом Unimat)
    for brand_name, api_url in PRODUCTS_API.items():
        print(f"Загрузка продуктов из API для бренда: {brand_name}...")
        products_data = fetch_data(api_url, is_post=True)
        
        if not products_data:
            print(f"Не удалось получить продукты для бренда {brand_name}. Пропускаем его.")
            continue
            
        # Проверяем, вернул ли API список товаров сразу или обернул его в словарь с ключом "products"
        product_list = products_data if isinstance(products_data, list) else products_data.get("products", [])
        
        # Проходим по каждому товару и принудительно записываем, откуда он пришел
        for product in product_list:
            product['source_brand'] = brand_name
        
        # Добавляем полученные товары в наш общий список
        all_products.extend(product_list)
        print(f"Успешно загружено {len(product_list)} товаров для бренда {brand_name}.")

    return all_products


# ==============================================================================
# 6. ГЛАВНАЯ ФУНКЦИЯ: СБОРКА И СОХРАНЕНИЕ XML-ФИДА
# ==============================================================================
def generate_xml_feed(products_list, categories_data, images_map):
    """
    Берет список всех товаров, категорий и картинок, трансформирует их 
    в структуру, требуемую Industrial.Market, и сохраняет в файл feed.xml.
    """
    # --------------------------------------------------------------------------
    # 6.1. Создаем шапку XML-документа
    # --------------------------------------------------------------------------
    # Тег <yml_catalog> с указанием текущей даты и времени
    root = ET.Element("yml_catalog", date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    
    # Тег <shop> (основной блок с информацией о магазине)
    shop = ET.SubElement(root, "shop")

    # Информация о вашей компании в каталоге
    ET.SubElement(shop, "name").text = "Prompower"
    ET.SubElement(shop, "company").text = "Мотрум"
    ET.SubElement(shop, "url").text = "https://brilka.github.io/prompower-feed/" 

    # --------------------------------------------------------------------------
    # 6.2. Создаем блок категорий <categories>
    # --------------------------------------------------------------------------
    categories_element = ET.SubElement(shop, "categories")
    
    if isinstance(categories_data, list):
        for category in categories_data:
            category_id = str(category.get("id"))
            category_title = category.get("title")
            
            # Записываем только те категории, у которых есть и ID, и Название
            if category_id and category_title:
                ET.SubElement(categories_element, "category", id=category_id).text = category_title

    # --------------------------------------------------------------------------
    # 6.3. Создаем блок товаров <offers>
    # --------------------------------------------------------------------------
    offers = ET.SubElement(shop, "offers")
    added_count = 0 # Счетчик добавленных товаров
    
    # Проходим по каждому товару из списка
    for product in products_list:
        
        # Берем артикул товара
        offer_id_or_article = product.get("article")
        
        # Если у товара нет артикула — мы не можем добавить его на маркетплейс, пропускаем
        if not offer_id_or_article:
            continue
            
        # ----------------------------------------------------------------------
        # ФИЛЬТРАЦИЯ 1: ПРОВЕРКА ЦЕНЫ
        # Требование: товары с нулевой или отсутствующей ценой добавлять НЕЛЬЗЯ!
        # ----------------------------------------------------------------------
        try:
            price_value = float(product.get("price", 0))
        except (ValueError, TypeError):
            price_value = 0 # Если вместо цены пришел текст или None

        # Если цена равна 0 или меньше — пропускаем товар (переходим к следующему)
        if price_value <= 0:
            continue

        # ----------------------------------------------------------------------
        # СОЗДАНИЕ КАРТОЧКИ ТОВАРА (<offer>)
        # ----------------------------------------------------------------------
        offer_id = str(offer_id_or_article)
        offer = ET.SubElement(offers, "offer", id=offer_id)
        added_count += 1 # Увеличиваем счетчик успешных товаров

        # Заполняем обязательные теги товара
        ET.SubElement(offer, "vendorCode").text = offer_id # Артикул производителя
        ET.SubElement(offer, "name").text = product.get("title", f"Продукт {offer_id}")
        ET.SubElement(offer, "categoryId").text = str(product.get("categoryId", "10")) 
        ET.SubElement(offer, "price").text = str(product.get("price", 0))
        ET.SubElement(offer, "vat").text = "7"              # Ставка НДС (7%)
        ET.SubElement(offer, "step-quantity").text = "1"    # Кратность заказа (по 1 шт.)
        ET.SubElement(offer, "preorder").text = "1"         # Разрешить предзаказ

        # Определяем Бренд и Производителя на основе источника
        source_brand = product.get('source_brand', 'Prompower')
        if source_brand == "Unimat":
            brand_name = "Unimat"
            vendor_name = "Unimat"
        else:
            brand_name = "Prompower"
            vendor_name = "Prompower"
            
        ET.SubElement(offer, "brand").text = brand_name
        ET.SubElement(offer, "vendor").text = vendor_name

        # ----------------------------------------------------------------------
        # ПРИВЯЗКА КАРТИНКИ ТОВАРА
        # ----------------------------------------------------------------------
        # Ищем картинку в нашей картотеке из внешнего XML по артикулу
        external_image = images_map.get(offer_id)
        
        if external_image:
            # Если нашли картинку во внешнем XML — используем её
            ET.SubElement(offer, "picture").text = external_image
        else:
            # Запасной вариант: если во внешнем XML картинки не было, берем из API
            api_image = product.get("picture", product.get("image"))
            if api_image:
                ET.SubElement(offer, "picture").text = api_image

        # Описание товара (если есть)
        description = product.get("description")
        if description:
            ET.SubElement(offer, "description").text = description 

        # ----------------------------------------------------------------------
        # ОСТАТКИ НА СКЛАДЕ И СКЛАД
        # ----------------------------------------------------------------------
        # Берем остаток товара (даже если он равен 0)
        quantity = int(product.get("instock", 0))
        
        # Создаем тег склада с указанным наименованием
        warehouse = ET.SubElement(offer, "warehouse", name="Главный склад Prompower и Unimat", unit="шт")
        warehouse.text = str(quantity)
        
        # ----------------------------------------------------------------------
        # ХАРАКТЕРИСТИКИ ТОВАРА (<param>)
        # ----------------------------------------------------------------------
        # Вес товара
        weight = product.get("weight")
        if weight:
             ET.SubElement(offer, "param", name="Вес", unit="кг").text = str(weight)
        
        # Габариты товара (длина x ширина x высота)
        height = product.get("height")
        width = product.get("width")
        depth = product.get("depth")
        
        if height and width and depth:
             dimensions = f"{height}x{width}x{depth}"
             ET.SubElement(offer, "param", name="Габариты", unit="мм").text = dimensions
        
    # --------------------------------------------------------------------------
    # 6.4. Форматирование XML и сохранение в файл
    # --------------------------------------------------------------------------
    # Превращаем дерево XML-тегов в байтовую строку
    rough_string = ET.tostring(root, 'utf-8')
    
    # Парсим строку с помощью minidom для красивого форматирования
    reparsed = minidom.parseString(rough_string)
    pretty_xml_as_string = reparsed.toprettyxml(indent="  ", encoding="utf-8").decode('utf-8')
    
    # Удаляем случайные пустые строки, которые иногда создает minidom
    pretty_xml_as_string = '\n'.join([line for line in pretty_xml_as_string.split('\n') if line.strip()])

    # Записываем итоговый текст в файл feed.xml в корне проекта
    with open("feed.xml", "w", encoding="utf-8") as f:
        f.write(pretty_xml_as_string)
    
    print(f"Готово! Файл feed.xml сгенерирован. Всего добавлено товаров: {added_count}")


# ==============================================================================
# 7. ТОЧКА ВХОДА (ПОСЛЕДОВАТЕЛЬНОСТЬ ЗАПУСКА СКРИПТА)
# ==============================================================================
if __name__ == "__main__":
    
    # --------------------------------------------------------------------------
    # ШАГ 0: ПРОВЕРКА ПАУЗЫ ПО ДАТЕ
    # --------------------------------------------------------------------------
    if PAUSE_UNTIL_DATE:
        try:
            # Превращаем текстовую дату из настройки в объект даты для сравнения
            pause_date = datetime.strptime(PAUSE_UNTIL_DATE, "%Y-%m-%d")
            
            # Сравниваем текущую дату с заданной датой паузы
            if datetime.now() < pause_date:
                print(f"=== ОБНОВЛЕНИЕ НА ПАУЗЕ ===")
                print(f"Сегодняшняя дата меньше, чем {PAUSE_UNTIL_DATE}.")
                print("Скрипт завершает работу без изменения файла feed.xml.")
                exit(0) # Успешно завершаем работу скрипта досрочно
        except ValueError:
            print("ОШИБКА: Неправильный формат даты в переменной PAUSE_UNTIL_DATE. Используйте формат YYYY-MM-DD (например, 2026-09-01).")

    # --------------------------------------------------------------------------
    # ШАГ 1: ПОЛУЧЕНИЕ КАТЕГОРИЙ
    # --------------------------------------------------------------------------
    categories = fetch_data(CATEGORIES_API_URL, is_post=False)
    if not categories:
        print("Критическая ошибка: Не удалось получить список категорий от API. Завершение работы.")
        exit(1) # Завершаем работу с кодом ошибки 1

    # --------------------------------------------------------------------------
    # ШАГ 2: ПОЛУЧЕНИЕ КАРТИНОК ИЗ ВНЕШНЕГО XML
    # --------------------------------------------------------------------------
    images_map = fetch_external_images_map()
        
    # --------------------------------------------------------------------------
    # ШАГ 3: ПОЛУЧЕНИЕ ВСЕХ ТОВАРОВ (PROMPOWER + UNIMAT)
    # --------------------------------------------------------------------------
    all_products = fetch_all_products()
    if not all_products:
        print("Критическая ошибка: Не удалось получить товары от API. Завершение работы.")
        exit(1) # Завершаем работу с кодом ошибки 1
        
    # --------------------------------------------------------------------------
    # ШАГ 4: СБОРКА И СОХРАНЕНИЕ XML-ФИДА
    # --------------------------------------------------------------------------
    generate_xml_feed(all_products, categories, images_map)
