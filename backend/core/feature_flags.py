import logging
from core.config import settings
try:
    from featureflags.client import CfClient
    from featureflags.evaluations.auth_target import Target
    HARNESS_AVAILABLE = True
except ImportError:
    HARNESS_AVAILABLE = False

logger = logging.getLogger(__name__)

class FeatureFlagsManager:
    def __init__(self):
        self.client = None
        self.target = None
        
        if HARNESS_AVAILABLE and settings.HARNESS_FF_SDK_KEY:
            try:
                self.client = CfClient(sdk_key=settings.HARNESS_FF_SDK_KEY)
                self.target = Target(identifier="demo", name="Demo Session")
                self.client.wait_for_initialization()
                logger.info("Harness Feature Flags client initialized.")
            except Exception as e:
                logger.error(f"Failed to init Harness FF: {e}")
        else:
            logger.warning("Harness FF SDK key not found or package not installed. Running in graceful fallback mode.")

    def is_order_creation_enabled(self) -> bool:
        """Kiểm tra flag enable_order_creation để biết có được phép tạo đơn thật không"""
        if self.client and self.target:
            try:
                return self.client.bool_variation("Enable_Order_Creation", self.target, False)
            except Exception as e:
                logger.error(f"Error checking feature flag: {e}")
        return False # Fallback an toàn

    def is_active(self) -> bool:
        return bool(self.client and self.target)

ff_manager = FeatureFlagsManager()
