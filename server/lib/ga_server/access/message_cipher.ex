defmodule GA.Access.MessageCipher do
  @moduledoc false
  @aad "ga-access-message:v1"

  def configured? do
    case Application.get_env(:ga_server, :access_encryption_key) do
      key when is_binary(key) and byte_size(key) == 32 -> true
      _ -> false
    end
  end

  def encrypt(message) do
    key = Application.fetch_env!(:ga_server, :access_encryption_key)
    nonce = :crypto.strong_rand_bytes(12)

    {ciphertext, tag} =
      :crypto.crypto_one_time_aead(:aes_256_gcm, key, nonce, message, @aad, 16, true)

    <<1, nonce::binary-size(12), tag::binary-size(16), ciphertext::binary>>
  end

  # Explicit administrative use only. There is deliberately no HTTP read endpoint.
  def decrypt(<<1, nonce::binary-size(12), tag::binary-size(16), ciphertext::binary>>) do
    key = Application.fetch_env!(:ga_server, :access_encryption_key)
    :crypto.crypto_one_time_aead(:aes_256_gcm, key, nonce, ciphertext, @aad, tag, false)
  end

  def decrypt(_), do: :error
end
