from django import forms
from .models import Dataset, DataFile, Notebook


class DatasetUploadForm(forms.ModelForm):
    tags_text = forms.CharField(
        required=False,
        label="Tags (comma separated)",
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "rodent, forelimb, skeletal, adult",
        }),
    )

    class Meta:
        model = Dataset
        fields = [
            "title", "abstract", "category", "license",
            "experiment_date", "lab", "institution",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. ERS_F Forelimb Morphometrics — Adult Cohort 2024",
            }),
            "abstract": forms.Textarea(attrs={
                "class": "form-textarea",
                "placeholder": "Describe the dataset, collection methodology, specimen details...",
            }),
            "category": forms.Select(attrs={"class": "form-select"}),
            "license": forms.Select(attrs={"class": "form-select"}),
            "experiment_date": forms.DateInput(attrs={
                "class": "form-input",
                "type": "date",
            }),
            "lab": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Dsenesky Lab",
            }),
            "institution": forms.TextInput(attrs={
                "class": "form-input",
                "placeholder": "e.g. Stanford University",
            }),
        }


class DataFileForm(forms.ModelForm):
    class Meta:
        model = DataFile
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-input"}),
        }


class NotebookForm(forms.ModelForm):
    class Meta:
        model = Notebook
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"class": "form-input"}),
        }
