defmodule GA.PublicLibraryExportTest do
  use ExUnit.Case, async: true

  @timestamp "2026-10-09T02:02:38+00:00"

  setup do
    root = Path.join(System.tmp_dir!(), "ga-public-export-#{System.unique_integer([:positive])}")
    directory = Path.join(root, "priv")
    File.mkdir_p!(Path.join(directory, "library"))
    File.mkdir_p!(Path.join(directory, "content"))
    File.mkdir_p!(Path.join(directory, "proofreading"))

    passage = write_content!(directory, "ga-001", "Reader text.")

    File.write!(
      Path.join(directory, "library/catalog.json"),
      Jason.encode!(%{
        works: [
          %{
            id: "ga-001",
            title: "Fixture work",
            state: "sanity_check",
            content_completeness: "complete",
            catalog_passage_count: 1,
            passages: [Map.take(passage, [:id, :title, :source_label, :checksum])],
            content_path: "/api/catalog/ga-001/content"
          },
          %{id: "ga-002", title: "Unavailable work", state: "import_queue"}
        ]
      })
    )

    File.write!(
      Path.join(directory, "proofreading/catalog.json"),
      Jason.encode!(%{generated_at: @timestamp})
    )

    for id <- ~w(ga-003 ga-004 ga-009 ga-010 ga-013) do
      write_content!(directory, id, "Reviewed reader text.")
    end

    on_exit(fn -> File.rm_rf!(root) end)
    {:ok, root: root, directory: directory}
  end

  test "all public catalog surfaces share the exact reader revision without private source",
       context do
    destination = export!(context, "initial")
    assert_surfaces!(destination, @timestamp)
  end

  test "layout changes produce updates and private source changes preserve the reader revision",
       context do
    initial = export!(context, "initial")
    initial_work = assert_surfaces!(initial, @timestamp)

    write_content!(context.directory, "ga-001", "Reader text.", %{
      page_anchors: [%{page: 2, start_offset: 0, source: "reviewed_source"}]
    })

    revised = export!(context, "layout-revision")
    revised_work = assert_surfaces!(revised, @timestamp)
    refute revised_work["content_revision"] == initial_work["content_revision"]
    assert revised_work["passages"] == initial_work["passages"]

    content_file = Path.join(context.directory, "content/ga-001.json")
    payload = read_json!(content_file)
    payload = put_in(payload, ["passages", Access.at(0), "source_text"], "New private source")
    File.write!(content_file, Jason.encode!(payload))

    source_only = export!(context, "source-only-revision")
    source_work = assert_surfaces!(source_only, @timestamp)
    assert source_work["content_revision"] == revised_work["content_revision"]
  end

  test "missing proofreading dates use stable library metadata", context do
    File.rm!(Path.join(context.directory, "proofreading/catalog.json"))
    catalog_file = Path.join(context.directory, "library/catalog.json")
    catalog = read_json!(catalog_file)
    fallback = "2026-10-08T12:00:00Z"
    File.write!(catalog_file, Jason.encode!(Map.put(catalog, "generated_at", fallback)))

    destination = export!(context, "fallback")
    assert_surfaces!(destination, fallback)
  end

  defp write_content!(directory, id, text, metadata \\ %{}) do
    passage = %{
      id: "#{id}-passage",
      title: "Fixture passage",
      source_label: "Fixture source",
      text: text,
      checksum: checksum(text),
      source_text: "Private source copy",
      metadata:
        Map.merge(
          %{
            source_text: "Private nested source",
            reading_blocks: [%{kind: "prose", start_offset: 0, end_offset: String.length(text)}]
          },
          metadata
        )
    }

    File.write!(
      Path.join(directory, "content/#{id}.json"),
      Jason.encode!(%{
        work_id: id,
        content_completeness: "complete",
        source_text: "Private payload source",
        passages: [passage]
      })
    )

    passage
  end

  defp export!(context, name) do
    destination = Path.join(context.root, name)
    bundled = Path.join(context.root, "#{name}-bundled.json")
    script = Path.expand("../../../tools/export_server_library.exs", __DIR__)

    expression =
      "Application.put_env(:ga_server, :catalog_priv_dir, #{inspect(context.directory)}); " <>
        "Code.require_file(#{inspect(script)})"

    {output, status} =
      System.cmd(
        "mix",
        [
          "run",
          "--no-start",
          "--no-compile",
          "--no-deps-check",
          "-e",
          expression,
          "--",
          destination,
          bundled
        ],
        cd: Path.expand("../..", __DIR__),
        env: [{"MIX_ENV", "test"}, {"GA_SKIP_REPO", "1"}],
        stderr_to_stdout: true
      )

    assert status == 0, output
    assert File.read!(bundled) == File.read!(Path.join(destination, "catalog.json"))
    destination
  end

  defp assert_surfaces!(destination, timestamp) do
    catalog = read_json!(Path.join(destination, "catalog.json"))
    assert read_json!(Path.join(destination, "api/catalog/index.json")) == catalog

    for work <- catalog["works"] do
      root = Path.join(destination, "api/catalog/#{work["id"]}")
      detail = read_json!(Path.join(root, "index.json"))["work"]
      manifest = read_json!(Path.join(root, "manifest"))
      assert detail == work

      if work["content_path"] do
        body = File.read!(Path.join(root, "content"))
        assert work["content_revision"] == checksum(body)
        assert work["content_updated_at"] == timestamp
        assert manifest["work"]["content_revision"] == work["content_revision"]
        assert manifest["work"]["content_updated_at"] == timestamp
        assert [bundle] = manifest["bundles"]
        assert bundle["checksum"] == work["content_revision"]
        assert bundle["byte_size"] == byte_size(body)
        assert bundle["passages"] == Enum.map(work["passages"], & &1["id"])
        assert Enum.all?(work["passages"], &(not Map.has_key?(&1, "metadata")))
      else
        refute Map.has_key?(work, "content_revision")
        refute Map.has_key?(work, "content_updated_at")
        refute Map.has_key?(manifest["work"], "content_revision")
        refute Map.has_key?(manifest["work"], "content_updated_at")
        assert manifest["bundles"] == []
      end
    end

    for path <- Path.wildcard(Path.join(destination, "**/*")), File.regular?(path) do
      refute String.contains?(File.read!(path), "source_text"), path
    end

    Enum.find(catalog["works"], &(&1["id"] == "ga-001"))
  end

  defp read_json!(path), do: path |> File.read!() |> Jason.decode!()
  defp checksum(body), do: :crypto.hash(:sha256, body) |> Base.encode16(case: :lower)
end
