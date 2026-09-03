import unittest
from dataclasses import replace

from llm_manager.application.apply_availability import (
    ApplyRoute,
    AssessProductionApplyAvailability,
)
from llm_manager.application.optimization import stable_hash
from llm_manager.domain.enums import HostKind
from tests.fixtures import plan, report


class ProductionApplyAvailabilityTests(unittest.TestCase):
    def test_all_four_routes_fail_closed_with_specific_reason(self) -> None:
        expected = {
            (HostKind.LOCAL, False): (ApplyRoute.LOCAL_USER, "local_user_apply_composition_missing"),
            (HostKind.LOCAL, True): (ApplyRoute.LOCAL_ROOT, "local_root_apply_composition_missing"),
            (HostKind.SSH, False): (ApplyRoute.SSH_USER, "ssh_user_apply_transport_missing"),
            (HostKind.SSH, True): (ApplyRoute.SSH_ROOT, "ssh_root_apply_protocol_missing"),
        }
        for (kind, requires_root), (route, reason) in expected.items():
            with self.subTest(kind=kind, requires_root=requires_root):
                observed = report()
                host = replace(
                    observed.host,
                    kind=kind,
                    ssh_alias="test-box" if kind is HostKind.SSH else None,
                )
                observed = replace(observed, host=host)
                current = plan()
                change = replace(current.change_set.changes[0], requires_root=requires_root)
                changes = replace(current.change_set, host_id=host.host_id, changes=(change,))
                current = replace(
                    current,
                    report_id=observed.report_id,
                    report_hash=stable_hash(observed),
                    change_set=changes,
                )
                availability = AssessProductionApplyAvailability().execute(current, observed)
                self.assertEqual(availability.route, route)
                self.assertFalse(availability.available)
                self.assertEqual(availability.reason_code, reason)

    def test_rejects_report_host_and_mixed_privilege_binding(self) -> None:
        observed = report()
        current = plan()
        service = AssessProductionApplyAvailability()
        with self.assertRaisesRegex(ValueError, "binding"):
            service.execute(current, observed)
        change = current.change_set.changes[0]
        changes = replace(
            current.change_set,
            host_id=observed.host.host_id,
            changes=(change, replace(change, change_id="root", requires_root=True)),
        )
        bound = replace(
            current,
            report_id=observed.report_id,
            report_hash=stable_hash(observed),
            change_set=changes,
        )
        with self.assertRaisesRegex(ValueError, "mixed_privilege"):
            service.execute(bound, observed)

    def test_only_explicitly_completed_route_is_available(self) -> None:
        observed = report()
        current = plan()
        change = replace(current.change_set.changes[0], requires_root=False)
        changes = replace(current.change_set, host_id=observed.host.host_id, changes=(change,))
        current = replace(
            current, report_id=observed.report_id,
            report_hash=stable_hash(observed), change_set=changes,
        )
        availability = AssessProductionApplyAvailability(
            frozenset({ApplyRoute.LOCAL_USER})
        ).execute(current, observed)
        self.assertTrue(availability.available)
        self.assertEqual(availability.reason_code, "available")


if __name__ == "__main__":
    unittest.main()
