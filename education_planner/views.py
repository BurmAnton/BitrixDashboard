from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import EducationProgramForm, ProgramSectionFormSet
from .models import EducationProgram

# Create your views here.

@login_required
def program_list(request):
    programs = EducationProgram.objects.all()
    return render(request, 'education_planner/program_list.html', {'programs': programs})

@login_required
def create_program(request):
    if request.method == 'POST':
        program_form = EducationProgramForm(request.POST)
        section_formset = ProgramSectionFormSet(request.POST)
        
        if program_form.is_valid() and section_formset.is_valid():
            program = program_form.save()
            sections = section_formset.save(commit=False)
            total_workload = 0
            for section in sections:
                section.program = program
                section.workload = (section.lecture_hours or 0) + (section.practice_hours or 0) + (section.selfstudy_hours or 0)
                total_workload += section.workload
                section.save()
            program.academic_hours = total_workload + (program.final_attestation or 0)
            program.save()
            messages.success(request, 'Программа успешно создана!')
            return redirect('education_planner:program_list')
    else:
        program_form = EducationProgramForm()
        section_formset = ProgramSectionFormSet()

    context = {
        'program_form': program_form,
        'section_formset': section_formset,
    }
    return render(request, 'education_planner/create_program.html', context)
