from django import forms
from .models import Review, DiscussionThread, DiscussionComment


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'title', 'body', 'is_spoiler']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-select form-select-sm bg-dark text-light border-secondary'}),
            'title': forms.TextInput(attrs={'class': 'form-control form-control-sm bg-dark text-light border-secondary', 'placeholder': 'Review title (optional)'}),
            'body': forms.Textarea(attrs={'class': 'form-control bg-dark text-light border-secondary', 'rows': 4, 'placeholder': 'Share your thoughts...'}),
            'is_spoiler': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_spoiler': 'Contains spoilers',
        }


class DiscussionThreadForm(forms.ModelForm):
    class Meta:
        model = DiscussionThread
        fields = ['title', 'body', 'episode_number', 'is_spoiler']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control form-control-sm bg-dark text-light border-secondary', 'placeholder': 'Thread title'}),
            'body': forms.Textarea(attrs={'class': 'form-control bg-dark text-light border-secondary', 'rows': 3, 'placeholder': 'Start the discussion...'}),
            'episode_number': forms.NumberInput(attrs={'class': 'form-control form-control-sm bg-dark text-light border-secondary', 'placeholder': 'Episode (optional)', 'min': 1}),
            'is_spoiler': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_spoiler': 'Contains spoilers',
        }


class DiscussionCommentForm(forms.ModelForm):
    class Meta:
        model = DiscussionComment
        fields = ['body', 'is_spoiler']
        widgets = {
            'body': forms.Textarea(attrs={'class': 'form-control form-control-sm bg-dark text-light border-secondary', 'rows': 2, 'placeholder': 'Write a comment...'}),
            'is_spoiler': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_spoiler': 'Spoiler',
        }
