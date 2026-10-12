defmodule GA.CatalogTest do
  use ExUnit.Case, async: true

  alias GA.Catalog

  test "reader catalog includes the full bundled library and unavailable works" do
    works = Catalog.list_reader_works()
    catalog = bundled_catalog()

    assert length(works) > 300

    assert MapSet.new(Enum.map(works, & &1.id)) ==
             MapSet.new(Enum.map(catalog["works"], & &1["id"]))

    assert Enum.any?(works, &(&1.state == "import_queue" and not Map.has_key?(&1, :content_path)))
    assert Enum.any?(works, &(&1.id == "ga-001" and is_binary(&1.content_path)))
    assert Enum.any?(works, &(&1.id == "ga-270-1"))

    for work <- works, passage <- work.passages do
      refute Map.has_key?(passage, :text)
      refute Map.has_key?(passage, :source_text)
    end
  end

  @tag timeout: 120_000
  test "every advertised download contains valid reader text matching its catalog metadata" do
    downloadable =
      Enum.filter(Catalog.list_reader_works(), &is_binary(Map.get(&1, :content_path)))

    assert length(downloadable) > 200

    for work <- downloadable do
      assert work.content_completeness == "complete"
      refute work.state == "published_seed"
      assert download = Catalog.download(work.id), "Missing reader bundle for #{work.id}"
      assert payload = Jason.decode!(download.body)
      assert payload["work_id"] == work.id
      assert payload["content_path"] == work.content_path
      assert payload["passage_count"] == length(payload["passages"])
      assert payload["content_completeness"] == "complete"
      refute payload["completeness"] in ["partial", "excerpt", "incomplete", "seed"]
      assert Enum.map(payload["passages"], & &1["id"]) == Enum.map(work.passages, & &1.id)
      assert download.byte_size == byte_size(download.body)

      assert download.checksum ==
               :crypto.hash(:sha256, download.body) |> Base.encode16(case: :lower)

      catalog_checksums = Map.new(work.passages, &{&1.id, &1.checksum})

      for passage <- payload["passages"] do
        assert is_binary(passage["text"]) and String.trim(passage["text"]) != ""
        checksum = :crypto.hash(:sha256, passage["text"]) |> Base.encode16(case: :lower)
        assert passage["checksum"] == checksum

        assert catalog_checksums[passage["id"]] == checksum,
               "Stale catalog checksum for #{passage["id"]}"

        refute Map.has_key?(passage, "source_text")
      end
    end
  end

  test "five production books retain original and normalized text for proofing" do
    for id <- ~w(ga-003 ga-004 ga-009 ga-010 ga-013) do
      work = Catalog.get_reader_work(id)
      content = Catalog.proofing_content(id)

      assert work.state == "published"
      assert work.proofing_state == "ai_checked"
      assert length(content["passages"]) >= 10
      assert content["proofing"]["source_retained_for_diff"]

      assert Enum.all?(content["passages"], fn passage ->
               is_binary(passage["source_text"]) and is_binary(passage["text"]) and
                 byte_size(passage["text"]) > 0
             end)

      refute Enum.any?(Catalog.content(id)["passages"], &Map.has_key?(&1, "source_text"))
    end
  end

  test "GA 004 exposes linked author annotations without appending them to reader text" do
    content = Catalog.content("ga-004")
    annotations = Enum.flat_map(content["passages"], &get_in(&1, ["metadata", "annotations"]))

    assert length(annotations) == 11
    assert Enum.any?(annotations, &(&1["marker"] == "(1)" && &1["text"] =~ "Psychologie"))

    refute Enum.any?(content["passages"], fn passage ->
             passage["metadata"]["annotations"] != [] and
               String.contains?(passage["text"], "Anmerkungen:")
           end)
  end

  test "developer catalog includes the complete GA source backlog" do
    works = Catalog.list_developer_works()

    assert length(works) > 300
    assert Enum.any?(works, &(&1.id == "ga-004" && &1.state == "published"))
    assert Enum.any?(works, &(&1.id == "ga-333"))
  end

  test "the complete GA 120 import is delivered through its existing content endpoint" do
    work = Catalog.get_work("ga-120")

    assert work.content_path == "/api/catalog/ga-120/content"

    content = Catalog.content("ga-120")
    assert content["work_id"] == "ga-120"
    assert content["content_path"] == "/api/catalog/ga-120/content"

    assert work.content_completeness == "complete"
    refute work.state == "published_seed"
    assert length(content["passages"]) == 11
    assert content["passage_count"] == 11
    assert Enum.all?(content["passages"], &String.contains?(&1["title"], "VORTRAG"))
    assert Enum.any?(content["passages"], &String.contains?(&1["title"], "ELFTER VORTRAG"))
    assert Enum.any?(content["passages"], &String.contains?(&1["text"], "Beobachtung des Lebens"))
  end

  test "catalog entries expose passage metadata without reader text" do
    work = Catalog.get_work("ga-120")

    assert length(work.passages) > 1
    assert Enum.all?(work.passages, &is_binary(&1.id))
    refute Enum.any?(work.passages, &Map.has_key?(&1, :text))
  end

  test "query and status filters search the full library" do
    assert Enum.any?(Catalog.list_reader_works(%{"q" => "GA 001"}), &(&1.id == "ga-001"))
    unavailable = Catalog.list_reader_works(%{"state" => "import_queue"})
    assert unavailable != []
    assert Enum.all?(unavailable, &(&1.state == "import_queue"))
  end

  defp bundled_catalog do
    :ga_server
    |> :code.priv_dir()
    |> to_string()
    |> Path.join("library/catalog.json")
    |> File.read!()
    |> Jason.decode!()
  end
end
