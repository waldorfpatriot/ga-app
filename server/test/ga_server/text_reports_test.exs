defmodule GA.Access.TextReportsTest do
  use GA.DataCase, async: true
  alias GA.Access
  alias GA.Access.{MessageCipher, TextReport, TextReports}
  @moduletag skip: System.get_env("GA_SKIP_REPO") in ["1", "true", "TRUE"]

  setup do
    {:ok, credentials} = Access.create_installation()
    %{installation: Access.authenticate(credentials.access_token)}
  end

  defp payload do
    %{
      "report_id" => Ecto.UUID.generate(),
      "book_id" => "ga-001",
      "section_id" => "chapter-1",
      "section_title" => "Vorwort",
      "selected_text" => " Ein Fähler. ",
      "selection_start" => 5,
      "selection_end" => 18,
      "message" => "Hier sollte Fehler stehen.",
      "app_version" => "1.0.1",
      "app_build" => "3",
      "platform" => "ios"
    }
  end

  test "inactive installations can submit confidential reports without granting access", %{
    installation: installation
  } do
    params = payload()
    assert {:ok, {:created, response}} = TextReports.submit(installation, params)
    assert response == %{status: "received", report_id: params["report_id"]}
    refute Access.status(installation).active
    stored = Repo.one!(TextReport)
    plaintext = MessageCipher.decrypt(stored.payload_ciphertext)
    assert Jason.decode!(plaintext) == params
    refute stored.payload_ciphertext =~ params["selected_text"]
    refute inspect(stored) =~ Base.encode16(stored.payload_fingerprint)
    assert [%{installation_id: id, payload: ^params}] = TextReports.list_for_operator()
    assert id == installation.id
    assert TextReports.list_for_operator(100, 1) == []
  end

  test "same UUID retries deduplicate and changed payload conflicts only within one installation",
       %{installation: installation} do
    params = payload()
    assert {:ok, {:created, _}} = TextReports.submit(installation, params)
    assert {:ok, {:replayed, _}} = TextReports.submit(installation, params)

    assert {:error, :report_conflict} =
             TextReports.submit(installation, Map.put(params, "message", "Andere Meldung"))

    assert Repo.aggregate(TextReport, :count) == 1
    {:ok, other} = Access.create_installation()

    assert {:ok, {:created, _}} =
             TextReports.submit(Access.authenticate(other.access_token), params)

    assert Repo.aggregate(TextReport, :count) == 2
  end

  test "validates Unicode scalar limits, required identifiers, metadata and UTF16 offset pairs",
       %{installation: installation} do
    params = payload()

    invalid = [
      %{"report_id" => nil},
      %{"report_id" => "oops"},
      %{"book_id" => "GA 1"},
      %{"book_id" => "../ga-001"},
      %{"section_id" => " "},
      %{"section_id" => String.duplicate("x", 201)},
      %{"selected_text" => "\n "},
      %{"selected_text" => 3},
      %{"selected_text" => String.duplicate("é", 4001)},
      %{"selected_text" => String.duplicate("😀", 8001)},
      %{"message" => String.duplicate("é", 1001)},
      %{"message" => 42},
      %{"section_title" => String.duplicate("a", 501)},
      %{"app_version" => 1},
      %{"app_build" => String.duplicate("a", 51)},
      %{"platform" => "android"},
      %{"selection_start" => nil},
      %{"selection_end" => nil},
      %{"selection_start" => -1},
      %{"selection_start" => 18},
      %{"selection_end" => 2_147_483_648},
      %{"selection_start" => 2.0},
      %{"selection_end" => "18"}
    ]

    for change <- invalid do
      assert {:error, :invalid_report} =
               TextReports.submit(installation, Map.merge(params, change))
    end

    assert {:error, :invalid_report} = TextReports.submit(installation, nil)
    assert Repo.aggregate(TextReport, :count) == 0

    params =
      Map.merge(params, %{
        "selected_text" => String.duplicate("😀", 8000),
        "message" => String.duplicate("😀", 2000),
        "selection_start" => nil,
        "selection_end" => nil
      })

    assert {:ok, {:created, _}} = TextReports.submit(installation, params)
  end

  test "retention erases whole report at 180 days, preserving retry/conflict receipt; deletion cascades",
       %{installation: installation} do
    now = DateTime.utc_now()
    old = payload()
    recent = payload()

    assert {:ok, {:created, _}} =
             TextReports.submit(installation, old, DateTime.add(now, -180, :day))

    assert {:ok, {:created, _}} =
             TextReports.submit(
               installation,
               recent,
               DateTime.add(now, -180 * 86400 + 1, :second)
             )

    assert {:ok, %{text_reports_deleted: 1}} = Access.prune_private_data(now)
    erased = Repo.get_by!(TextReport, report_id: old["report_id"])
    assert erased.payload_ciphertext == nil
    assert erased.payload_deleted_at == now
    assert erased.payload_fingerprint
    assert [%{payload: ^recent}] = TextReports.list_for_operator()
    assert {:ok, {:replayed, _}} = TextReports.submit(installation, old, now)

    assert {:error, :report_conflict} =
             TextReports.submit(installation, Map.put(old, "message", "geändert"), now)

    assert Repo.get!(TextReport, erased.id).payload_ciphertext == nil
    assert {:ok, _} = Access.delete_installation(installation)
    assert Repo.aggregate(TextReport, :count) == 0
  end
end
