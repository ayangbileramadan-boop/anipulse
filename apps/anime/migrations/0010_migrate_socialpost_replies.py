from django.db import migrations


def migrate_replies(apps, schema_editor):
    SocialPost = apps.get_model('anime', 'SocialPost')
    Comment = apps.get_model('anime', 'Comment')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ctype = ContentType.objects.get_for_model(SocialPost)
    qs = SocialPost.objects.filter(reply_to__isnull=False).select_related('reply_to').order_by('created_at')
    migrated = 0
    for post in qs:
        existing = Comment.objects.filter(
            content_type=ctype, object_id=post.reply_to_id,
            user=post.user, created_at=post.created_at
        ).exists()
        if existing:
            continue
        Comment.objects.create(
            user=post.user,
            body=post.body,
            content_type=ctype,
            object_id=post.reply_to_id,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )
        migrated += 1
    if migrated:
        print(f'Migrated {migrated} old SocialPost replies to Comment model')


class Migration(migrations.Migration):
    dependencies = [
        ('anime', '0009_comment_commentlike_and_more'),
    ]
    operations = [
        migrations.RunPython(migrate_replies, migrations.RunPython.noop),
    ]
