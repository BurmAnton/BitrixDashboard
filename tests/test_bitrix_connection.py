from fast_bitrix24 import Bitrix
from django.conf import settings

def test_bitrix_connection():
    try:
        # Создаем экземпляр класса Bitrix
        webhook = settings.BITRIX24_SETTINGS['CLIENT_SECRET']
        domain = settings.BITRIX24_SETTINGS['DOMAIN']
        bitrix = Bitrix(f'{domain}/rest/{webhook}/')
        print(f'{domain}/rest/{webhook}')
        # Пробуем получить информацию о текущем пользователе
        result = bitrix.get_all('crm.contact.fields')
        
        if result:
            print("✅ Подключение успешно!")
            print("Данные пользователя:", result)
            return True
        else:
            print("❌ Ошибка подключения: нет данных")
            return False
            
    except Exception as e:
        print("❌ Произошла ошибка при подключении:")
        print(str(e))
        return False

if __name__ == "__main__":
    test_bitrix_connection() 