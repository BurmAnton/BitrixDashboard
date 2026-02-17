from django import forms

class ContactImportFromExcel(forms.Form):
    excel_file = forms.FileField(
        label='Excel таблица с данными',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept':'.xlsx, .xls'})
    )
    type = forms.ChoiceField(
        label='Импортирумные данные',
        choices=[('','---------')]+[('contacts','Контакты'),('orgs','Организации')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    