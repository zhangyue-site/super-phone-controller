"""Host guardrails for native CDC authorization (hardware validation is separate)."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
K = ROOT / 'app/android/app/src/main/kotlin/org/example/phonecontroller'
class UsbNativeContract(unittest.TestCase):
    def test_bounded_correlated_cdc_only(self):
        s=(K/'UsbProofBridge.kt').read_text()
        for token in ('getInterface(0)', 'getInterface(1)', 'USB_CLASS_COMM', 'USB_CLASS_CDC_DATA', 'USB_ENDPOINT_XFER_BULK', '0x22', 'TIMEOUT_MS', 'MAX_BYTES', 'SecureRandom', 'PCUSB $requestId', 'startsWith(prefix)', 'releaseInterface', 'connection.close()', 'hasPermission(device)', 'device.deviceId', 'usbSerial', 'proof'):
            self.assertIn(token,s)
        self.assertNotIn('UsbConstants.USB_CLASS_HID',s)
    def test_rapid_same_board_reattach_revokes_old_consent(self):
        import subprocess,tempfile
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'UsbLeaseHarness.java'
            source.write_text('''import org.example.phonecontroller.UsbSessionLease;
public class UsbLeaseHarness {
 public static void main(String[] args) {
  UsbSessionLease lease=new UsbSessionLease();
  String pending=lease.attach("AABBCCDDEEFF");
  long proofGeneration=lease.generation();
  if(!lease.matches(pending))throw new AssertionError("initial lease");
  String revoked=lease.detach();
  if(!pending.equals(revoked)||lease.matches(pending))throw new AssertionError("detach must revoke immediately");
  String fresh=lease.attach("AABBCCDDEEFF");
  if(fresh.equals(pending)||lease.matches(pending)||!lease.matches(fresh))throw new AssertionError("rapid reattach must require fresh consent");
  if(proofGeneration==lease.generation())throw new AssertionError("old CDC proof must be fenced");
 }
}''')
            subprocess.run(['javac','-d',temp,str(ROOT/'app/android/app/src/main/java/org/example/phonecontroller/UsbSessionLease.java'),str(source)],check=True,capture_output=True)
            subprocess.run(['java','-cp',temp,'UsbLeaseHarness'],check=True,capture_output=True)
        bridge=(K/'UsbLaunchBridge.kt').read_text()
        self.assertNotIn('handler.postDelayed',bridge)
        self.assertIn('session=null',bridge)
        self.assertIn('oldSession?.let { lost?.invoke(it) }',bridge)
        self.assertIn('lease.detach()',bridge)
        self.assertIn('val detachGeneration: Long get()=lease.generation()',bridge)
    def test_lifecycle_and_session_guards(self):
        s=(K/'UsbProofBridge.kt').read_text()
        self.assertIn('Executors.newSingleThreadExecutor',s)
        self.assertGreaterEqual(s.count('UsbLaunchBridge.matches(session)'),2)
        self.assertIn('UsbLaunchBridge.detachGeneration!=generation',s)
        self.assertIn('fun close()',s)
        self.assertIn('pending?.error',s)
        activity=(K/'MainActivity.kt').read_text()
        self.assertIn('"info", "sign"',activity)
        self.assertIn('usbProof?.close()',activity)
if __name__ == '__main__': unittest.main()
