from django.db import migrations

def seed_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Standard User
    standard_user, _ = Group.objects.get_or_create(name='Standard User')
    standard_perms = Permission.objects.filter(codename__in=[
        # Contacts
        'add_contact', 'view_contact', 'change_contact', 'delete_contact',
        # Events
        'add_event', 'view_event', 'change_event', 'delete_event',
        # Journal
        'add_journalentry', 'view_journalentry',
    ])
    standard_user.permissions.set(standard_perms)

    # Admin
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    admin_perms = Permission.objects.filter(codename__in=[
        # User account management
        'add_user',
        'view_user',
        'change_user',
        'delete_user',
        # Group/Permission management
        'add_group',
        'view_group',
        'change_group',
        'delete_group',
        'add_permission',
        'view_permission',
        # Session management
        'delete_session',
        'view_session',
    ])
    admin_group.permissions.set(admin_perms)

    # Third-Party Viewer
    viewer, _ = Group.objects.get_or_create(name="Third-Party Viewer")
    viewer_perms = Permission.objects.filter(codename__in=[
        'view_contact',
        'view_event',
        'view_journalentry',
    ])
    viewer.permissions.set(viewer_perms)

def reverse_seed_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=[
        'Standard User', 'Admin', 'Third-Party Viewer'
    ]).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(seed_groups, reverse_seed_groups),
    ]