from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from .models import Organization, Region, OrganizationType, HistoryOrganization, ContactEmail, ContactPhone
from .forms import ContactImportFromExcel
from datetime import datetime
import openpyxl

def ExcelImportOrganization(form):
    if form.is_valid():
        excel_file = form.cleaned_data['excel_file']

        try:
            wb = openpyxl.load_workbook(excel_file)
            ws = wb.active
        except Exception as e:
            return False, f'Ошибка при открытии файла: {e}'

        created = 0
        updated = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            inn = row[0]
            name = row[1]
            full_name = row[2]
            type_name = row[3]
            federal_company = True if row[4] is not None else False
            region_name = row[5]
            parent_company_inn = row[6]

            OrgType = OrganizationType.objects.filter(name=type_name).first()
            region = Region.objects.filter(name=region_name).first()
            parent_company = Organization.objects.filter(inn=parent_company_inn) or None

            obj_history = Organization.objects.filter(inn=inn).first()
            if obj_history:       
                HistoryOrganization.objects.create(
                    organization=obj_history,
                    name=obj_history.name,
                    status='active',
                    date=datetime.now()
                )
                updated += 1
            else: created += 1

            Organization.objects.update_or_create(
                inn=inn,
                defaults={
                    'name': name,
                    'full_name': full_name,
                    'type': OrgType,
                    'federal_company': federal_company,
                    'region': region,
                    'parent_company': parent_company
                }
            )
        return True, f"Результат: Успешный импорт, Добавлено: {created}, Обновлено: {updated}"
    return False, f"Ошибка: Не корректная форма"

def ExcelImportContact(form):
    if form.is_valid():
        excel_file = form.cleaned_data['excel_file']

        try:
            wb = openpyxl.load_workbook(excel_file)
            ws = wb.active
        except Exception as e:
            return False, f'Ошибка при открытии файла: {e}'
        created_person = 0
        created_main = 0
        created_department = 0
        for SheetName in wb.sheetnames:
            if wb[SheetName] == "По сотрудникам":
                for row in ws.iter_rows(min_row=2, values_only=True):
                    inn = row[0]
                    last_name = row[1]
                    first_name = row[2]
                    middle_name = row[3]
                    position = row[4]
                    last_name_dat = row[5]
                    first_name_dat = row[6]
                    middle_name_dat = row[7]
                    position_dat = row[8]
                    manager = True if row[9] else False
                    phone = row[10]
                    email = row[11]
                    comment = row[12]


                    organization = Organization.objects.filter(inn=inn).first()
                    if organization:
                        created_person += 1
                        obj = Organization.objects.create(
                            organization=organization,
                            type='person',
                            defaults={
                                'first_name': first_name,
                                'last_name': last_name,
                                'middle_name': middle_name,
                                'position': position,
                                'first_name_dat': first_name_dat,
                                'last_name_dat': last_name_dat,
                                'middle_name_dat': middle_name_dat,
                                'position_dat': position_dat,
                                'manager': manager,
                                'comment': comment                        
                            }
                        )
                        if email:
                            ContactEmail.objects.create(
                                contact=obj,
                                email = email
                            )
                        if phone:
                            ContactPhone.objects.create(
                                contact=obj,
                                number=phone
                            )
            elif wb[SheetName] == "По отделам":
                for row in ws.iter_rows(min_row=2, values_only=True):
                    inn = row[0]
                    department_name = row[1]
                    phone = row[2]
                    email = row[3]
                    comment = row[4]

                    organization = Organization.objects.filter(inn=inn).first()
                    if organization:
                        created_department += 1
                        obj = Organization.objects.update_or_create(
                            organization=organization,
                            defaults={
                                'type': 'department',
                                'first_name': first_name,
                                'department_name': department_name,
                                'comment': comment                        
                            }
                        )
                        if email:
                            ContactEmail.objects.create(
                                contact=obj,
                                email = email
                            )
                        if phone:
                            ContactPhone.objects.create(
                                contact=obj,
                                number=phone
                            )
            elif wb[SheetName] == "Главный контакт":
                for row in ws.iter_rows(min_row=2, values_only=True):
                    inn = row[0]
                    phone = row[1]
                    email = row[2]
                    comment = row[3]


                    organization = Organization.objects.filter(inn=inn).first()
                    if organization:
                        created_main += 1
                        obj = Organization.objects.update_or_create(
                            organization=organization,
                            defaults={
                                'type': 'department',
                                'first_name': first_name,
                                'comment': comment                        
                            }
                        )
                        if email:
                            ContactEmail.objects.create(
                                contact=obj,
                                email = email
                            )
                        if phone:
                            ContactPhone.objects.create(
                                contact=obj,
                                number=phone
                            )
        return True, f'Импорт завершен успешно. Создано контактов: {created_person} сотрудников, {created_department} отделов, {created_main} основных контактов.'
    return False,f'Форма не валидна'
   
def ContactImport(request):
    if not request.user.is_authenticated:
        messages.warning(request, 'Для доступа к импорту необходимо войти в систему.')
        return redirect(f'{settings.LOGIN_URL}?next={request.path}')
    if request.method == 'POST':
        form = ContactImportFromExcel(request.POST,request.FILES)
        if form.is_valid():
            if form.cleaned_data['type'] == 'contacts':
                success, msg = ExcelImportContact(form)
                messages.success(request, msg) if success else messages.error(request, msg)
            elif form.cleaned_data['type'] == 'orgs':
                success, msg = ExcelImportOrganization(form)
                messages.success(request, msg) if success else messages.error(request, msg)
        else:
            print("Form errors:", form.errors)
            messages.error(request, "Не валидная форма")
    else:
        form = ContactImportFromExcel()

    return render(request,"contact_management/import_form.html", {'form': form})
