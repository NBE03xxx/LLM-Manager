import unittest

from llm_manager.application.restore_availability import (
    AssessProductionRestoreAvailability,
    RestoreRoute,
)
from llm_manager.domain.enums import HostKind


class ProductionRestoreAvailabilityTests(unittest.TestCase):
    def test_all_four_routes_fail_closed_with_specific_reason(self) -> None:
        expected = {
            (HostKind.LOCAL, False): (RestoreRoute.LOCAL_USER, "local_user_restore_composition_missing"),
            (HostKind.LOCAL, True): (RestoreRoute.LOCAL_ROOT, "local_root_restore_protocol_missing"),
            (HostKind.SSH, False): (RestoreRoute.SSH_USER, "ssh_user_restore_protocol_missing"),
            (HostKind.SSH, True): (RestoreRoute.SSH_ROOT, "ssh_root_restore_protocol_missing"),
        }
        service = AssessProductionRestoreAvailability()
        for arguments, result in expected.items():
            with self.subTest(arguments=arguments):
                availability = service.execute(*arguments)
                self.assertEqual((availability.route, availability.reason_code), result)
                self.assertFalse(availability.available)

    def test_only_explicitly_completed_route_is_available(self) -> None:
        service = AssessProductionRestoreAvailability(frozenset({RestoreRoute.LOCAL_USER}))
        local = service.execute(HostKind.LOCAL, False)
        remote = service.execute(HostKind.SSH, False)
        self.assertTrue(local.available)
        self.assertEqual(local.reason_code, "available")
        self.assertFalse(remote.available)


if __name__ == "__main__":
    unittest.main()
