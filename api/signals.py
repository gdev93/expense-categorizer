from django.conf import settings
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from allauth.account.signals import user_signed_up, email_confirmed
from allauth.account.models import EmailAddress

from .models import UploadFile, FileStructureMetadata


@receiver(user_signed_up)
def send_welcome_email_on_signup(request, user, **kwargs):
    """
    Sends a welcome email when a user signs up, but only if they are already verified
    (e.g. social login with pre-verified email).
    """
    if EmailAddress.objects.filter(user=user, verified=True).exists():
        send_welcome_email_to_user(user, request)


@receiver(email_confirmed)
def send_welcome_email_on_confirmation(request, email_address, **kwargs):
    """
    Sends a welcome email when a user confirms their email address.
    """
    send_welcome_email_to_user(email_address.user, request)


def send_welcome_email_to_user(user, request):
    """
    Helper function to send the welcome email and track it in the user's profile.
    """
    # Ensure profile exists and email hasn't been sent yet
    if not hasattr(user, 'profile') or user.profile.welcome_email_sent:
        return

    protocol = 'https' if request.is_secure() else 'http'
    site_url = f"{protocol}://{settings.SITE_NAME}"

    context = {
        'user': user,
        'site_url': site_url,
    }

    subject = render_to_string('account/email/welcome_subject.txt', context).strip()
    html_content = render_to_string('account/email/welcome_message.html', context)
    text_content = render_to_string('account/email/welcome_message.txt', context)

    msg = EmailMultiAlternatives(subject, text_content, None, [user.email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()

    # Mark as sent
    user.profile.welcome_email_sent = True
    user.profile.save()


@receiver(pre_save, sender=UploadFile)
def create_file_structure_metadata(sender, instance: UploadFile, **kwargs):
    """
    Signal to automatically create FileStructureMetadata
    when an UploadFile entry is updated with structure information.
    """
    # Only proceed if we have the minimum required columns set and the instance exists
    if instance.pk and instance.description_column_name and instance.date_column_name and (
            instance.income_amount_column_name or instance.expense_amount_column_name):

        first_transaction = instance.transactions.first()
        if not first_transaction:
            return

        keys = first_transaction.raw_data.keys()
        row_hash = FileStructureMetadata.generate_tuple_hash(keys)

        # Use get_or_create to avoid duplicates if the same structure
        # is uploaded by different files/users
        fsm, _ = FileStructureMetadata.objects.get_or_create(
            row_hash=row_hash,
            defaults={
                'description_column_name': instance.description_column_name,
                'income_amount_column_name': instance.income_amount_column_name,
                'expense_amount_column_name': instance.expense_amount_column_name,
                'date_column_name': instance.date_column_name,
                'merchant_column_name': instance.merchant_column_name,
                'operation_type_column_name': instance.operation_type_column_name,
                'notes': instance.notes,
            }
        )
        instance.file_structure_metadata = fsm
        # Do NOT call instance.save() here as it is a pre_save signal
