from django.test import TestCase, override_settings
from django.core import signing
from users.models import User
from organizations.models import Organization


@override_settings(LUNOR_JWT_ENABLED=False)
class UserAuthenticateOrgTests(TestCase):
    def test_create_org_for_new_user_when_is_org_true(self):
        payload = {
            'email': 'org@example.com',
            'lunor_userId': 'org123',
            'is_org': True,
            'organization': 'Acme Org',
        }
        token = signing.dumps(payload, salt='ls-auth-token')
        resp = self.client.get(f'/user/authenticate/?token={token}')
        # User should be created
        user = User.objects.get(email='org@example.com')
        # Organization created and linked to user as owner
        org = Organization.objects.get(created_by=user)
        self.assertEqual(org.title, 'Acme Org')
        user.refresh_from_db()
        self.assertEqual(user.active_organization, org)

    def test_existing_user_gets_new_org_if_is_org_true_and_no_membership(self):
        user = User.objects.create_user(email='existing@example.com', password='pw', lunor_userId='existing123')
        payload = {
            'email': 'existing@example.com',
            'lunor_userId': 'existing123',
            'is_org': True,
            'organization': 'Existing Org',
        }
        token = signing.dumps(payload, salt='ls-auth-token')
        resp = self.client.get(f'/user/authenticate/?token={token}')
        org = Organization.objects.get(created_by=user)
        self.assertEqual(org.title, 'Existing Org')
        user.refresh_from_db()
        self.assertEqual(user.active_organization, org)
