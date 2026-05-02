from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase

from contacts.tests.factories import UserFactory
from lookups.models import FactCategory


class FactCategoryModelTests(TestCase):
    def test_str_returns_name(self):
        category = FactCategory.objects.create(
            name="Health",
            icon_reference="FiHeart",
            is_system_default=True,
        )

        self.assertEqual(str(category), "Health")

    def test_db_table_is_fact_categories(self):
        self.assertEqual(FactCategory._meta.db_table, "fact_categories")

    def test_parent_accepts_fact_category_and_exposes_children(self):
        parent = FactCategory.objects.create(name="Health", is_system_default=True)
        child = FactCategory.objects.create(
            parent=parent,
            name="Allergies",
            is_system_default=True,
        )

        self.assertEqual(child.parent, parent)
        self.assertEqual(list(parent.children.all()), [child])


class FactCategoryViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.other_user = UserFactory()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_visible_root_fact_categories(self):
        system_root = FactCategory.objects.create(
            name="Health",
            icon_reference="FiHeart",
            is_system_default=True,
        )
        user_root = FactCategory.objects.create(
            user=self.user,
            name="Personal",
            icon_reference="FiUser",
        )
        other_root = FactCategory.objects.create(
            user=self.other_user,
            name="Other",
            icon_reference="FiUsers",
        )
        FactCategory.objects.create(
            parent=system_root,
            name="Allergies",
            icon_reference="FiAlertCircle",
            is_system_default=True,
        )

        response = self.client.get(reverse("fact-category-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        category_ids = {category["id"] for category in response.data}
        self.assertIn(system_root.id, category_ids)
        self.assertIn(user_root.id, category_ids)
        self.assertNotIn(other_root.id, category_ids)

    def test_list_serializes_visible_children_recursively(self):
        root = FactCategory.objects.create(
            name="Health",
            icon_reference="FiHeart",
            is_system_default=True,
        )
        visible_child = FactCategory.objects.create(
            parent=root,
            name="Allergies",
            icon_reference="FiAlertCircle",
            is_system_default=True,
        )
        visible_grandchild = FactCategory.objects.create(
            parent=visible_child,
            user=self.user,
            name="Food",
            icon_reference="FiCoffee",
        )
        other_child = FactCategory.objects.create(
            parent=root,
            user=self.other_user,
            name="Private",
            icon_reference="FiLock",
        )

        response = self.client.get(reverse("fact-category-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        root_data = next(category for category in response.data if category["id"] == root.id)
        child_ids = {child["id"] for child in root_data["children"]}
        self.assertIn(visible_child.id, child_ids)
        self.assertNotIn(other_child.id, child_ids)

        child_data = next(
            child for child in root_data["children"] if child["id"] == visible_child.id
        )
        grandchild_ids = {
            grandchild["id"] for grandchild in child_data["children"]
        }
        self.assertIn(visible_grandchild.id, grandchild_ids)

    def test_detail_categories_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("detail-category-list")

    def test_detail_categories_path_is_removed(self):
        response = self.client.get("/api/lookups/detail-categories/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
