package com.local.fenbistudy.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.net.URL

class LanRequestSignerTest {
    @Test
    fun signatureIsStableAndVerifiable() {
        val signer = LanRequestSigner("correct horse battery staple".toByteArray())
        val value = signer.sign("POST", "/capture/task/4", 1234L, "abc")
        assertEquals(value, signer.sign("POST", "/capture/task/4", 1234L, "abc"))
        assertTrue(signer.verify(value, "POST", "/capture/task/4", 1234L, "abc"))
        assertFalse(signer.verify(value, "POST", "/capture/task/5", 1234L, "abc"))
    }

    @Test
    fun insecureRemoteEndpointsAreRejected() {
        assertTrue(isSecureTransferEndpoint(URL("https://192.168.1.20:8443")))
        assertTrue(isSecureTransferEndpoint(URL("http://127.0.0.1:8765")))
        assertTrue(isSecureTransferEndpoint(URL("http://192.168.1.20:8765")))
        assertFalse(isSecureTransferEndpoint(URL("http://8.8.8.8:8765")))
        assertFalse(isSecureTransferEndpoint(URL("http://example.com:8765")))
    }

    @Test
    fun pairingCodeParsesPrivateHttpEndpoint() {
        val parsed = parsePairingCode("FENBI1|http://192.168.1.8:17831|correct-horse-battery")
        assertTrue(parsed != null)
        assertEquals("192.168.1.8", parsed!!.first.host)
        assertEquals(17831, parsed.first.port)
        assertFalse(parsePairingCode("FENBI1|http://8.8.8.8:17831|correct-horse-battery") != null)
    }
}
