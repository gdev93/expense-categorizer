import os
from typing import Any
from django.conf import settings
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from allauth.account.signals import user_signed_up, email_confirmed
from allauth.account.models import EmailAddress
from django.contrib.auth.models import User

from .models import UploadFile, FileStructureMetadata, Transaction, Profile

is_secure = os.getenv('ENV','local') == 'prod'

@receiver(user_signed_up)
def send_welcome_email_on_signup(request: Any, user: User, **kwargs: Any) -> None:
    """
    Sends a welcome email when a user signs up, but only if they are already verified
    (e.g. social login with pre-verified email).
    """
    if EmailAddress.objects.filter(user=user, verified=True).exists():
        send_welcome_email_to_user(user, request)
        send_backoffice_notification(request, user)


@receiver(email_confirmed)
def send_welcome_email_on_confirmation(request: Any, email_address: Any, **kwargs: Any) -> None:
    """
    Sends a welcome email when a user confirms their email address.
    """
    send_welcome_email_to_user(email_address.user, request)
    send_backoffice_notification(request, email_address.user)

def send_backoffice_notification(request: Any, user: User, **kwargs: Any) -> None:
    """
    Sends a notification email to the backoffice when a new user signs up.
    """
    if not settings.BACKOFFICE_EMAIL:
        return

    protocol = 'https' if is_secure else 'http'
    site_url = f"{protocol}://{settings.SITE_NAME}"

    context = {
        'user': user,
        'site_url': site_url,
    }

    subject = render_to_string('backoffice/email/new_user_subject.txt', context).strip()
    html_content = render_to_string('backoffice/email/new_user_message.html', context)
    text_content = render_to_string('backoffice/email/new_user_message.txt', context)

    msg = EmailMultiAlternatives(subject, text_content, None, [settings.BACKOFFICE_EMAIL])
    msg.attach_alternative(html_content, "text/html")
    msg.send()


def send_welcome_email_to_user(user: User, request: Any) -> None:
    """
    Helper function to send the welcome email and track it in the user's profile.
    """
    # Ensure profile exists and email hasn't been sent yet
    if not hasattr(user, 'profile') or user.profile.welcome_email_sent:
        return

    protocol = 'https' if is_secure else 'http'
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
def create_file_structure_metadata(sender: Any, instance: UploadFile, **kwargs: Any) -> None:
    """
    Signal to automatically create FileStructureMetadata
    when an UploadFile entry is updated with structure information.
    """
    # Only proceed if we have the minimum required columns set and the instance exists
    if instance.pk and instance.description_column_name and instance.date_column_name and (
            instance.income_amount_column_name or instance.expense_amount_column_name):

        first_transaction = instance.transactions.first()
        if not first_transaction or not first_transaction.raw_data:
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


@receiver([post_save, post_delete], sender=Transaction)
def mark_rollup_dirty_on_transaction_change(sender: Any, instance: Transaction, **kwargs: Any) -> None:
    """Mark the user's profile as needing rollup recomputation when a transaction changes."""
    Profile.objects.filter(user=instance.user, needs_rollup_recomputation=False).update(needs_rollup_recomputation=True)


@receiver(post_delete, sender=UploadFile)
def mark_rollup_dirty_on_upload_delete(sender: Any, instance: UploadFile, **kwargs: Any) -> None:
    """Mark the user's profile as needing rollup recomputation when an upload is deleted."""
    Profile.objects.filter(user=instance.user, needs_rollup_recomputation=False).update(needs_rollup_recomputation=True)
