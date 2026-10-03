import os
import unittest
from unittest import mock

os.environ.setdefault("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/z")

import email_envio  # noqa: E402


class EmailTesteTeste(unittest.TestCase):
    def test_dominios_reservados(self):
        self.assertTrue(email_envio.email_de_teste("a@example.com"))
        self.assertTrue(email_envio.email_de_teste("a@escola.test"))
        self.assertFalse(email_envio.email_de_teste("a@gmail.com"))

    def test_dominios_configurados(self):
        with mock.patch.dict(os.environ, {"EMAIL_DOMINIOS_TESTE": "semente-teste.com.br"}):
            self.assertTrue(email_envio.email_de_teste("diego@semente-teste.com.br"))
            self.assertFalse(email_envio.email_de_teste("diego@semente.com.br"))

    def test_modo_teste_nao_envia(self):
        with mock.patch.dict(os.environ, {"EMAIL_MODO_TESTE": "1"}), \
                mock.patch.object(email_envio, "_enviar_via_https") as https, \
                mock.patch.object(email_envio, "_tentar_smtp_gmail") as smtp:
            enviados = email_envio.enviar_email(["a@gmail.com"], "Assunto", "Corpo")
        self.assertEqual(enviados, ["a@gmail.com"])
        https.assert_not_called()
        smtp.assert_not_called()

    def test_so_destinos_de_teste_nao_envia(self):
        with mock.patch.dict(os.environ, {"EMAIL_MODO_TESTE": ""}), \
                mock.patch.object(email_envio, "carregar_smtp") as smtp:
            enviados = email_envio.enviar_email(["a@example.com"], "Assunto", "Corpo")
        self.assertEqual(enviados, ["a@example.com"])
        smtp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
