# Run from server/: GA_SKIP_REPO=1 mix run ../tools/export_server_library.exs OUTPUT_DIRECTORY [BUNDLED_CATALOG_FILE]
# Serve the generated tree with JSON MIME types and index.json directory indexes.
defmodule GA.PublicLibraryExport do
  alias GA.Catalog

  def run(arguments) do
    {destination, bundled_catalog} =
      case arguments do
        [destination] ->
          {Path.expand(destination), nil}

        [destination, bundled_catalog] ->
          {Path.expand(destination), Path.expand(bundled_catalog)}

        _ ->
          raise "Usage: mix run ../tools/export_server_library.exs OUTPUT_DIRECTORY [BUNDLED_CATALOG_FILE]"
      end

    if File.exists?(destination) do
      raise "Export destination already exists. Choose a new directory: #{destination}"
    end

    staging = destination <> ".building-#{System.unique_integer([:positive])}"

    try do
      works = Catalog.list_reader_works()

      if works == [], do: raise("Cannot export an empty public library")

      for work <- works do
        if work.state == "published_seed" do
          raise "Refusing to export a published seed or excerpt: #{work.id}"
        end

        if is_binary(Map.get(work, :content_path)) and work.content_completeness != "complete" do
          raise "Refusing to advertise an incomplete volume: #{work.id}"
        end
      end

      content_updated_at = content_updated_at()

      {works, download_count, download_bytes} =
        Enum.reduce(works, {[], 0, 0}, fn work, {exported, count, bytes} ->
          if is_binary(Map.get(work, :content_path)) do
            download =
              Catalog.download(work.id) || raise "Missing or invalid download for #{work.id}"

            assert_reader_safe!(download.payload)

            if download.payload["content_completeness"] != "complete" or
                 Map.get(download.payload, "completeness", "complete") != "complete" do
              raise "Refusing to export a partial or excerpt payload: #{work.id}"
            end

            if Enum.map(download.payload["passages"], & &1["id"]) !=
                 Enum.map(work.passages, & &1.id) do
              raise "Catalog passage metadata differs from download for #{work.id}"
            end

            catalog_checksums = Map.new(work.passages, &{&1.id, &1.checksum})

            for passage <- download.payload["passages"] do
              checksum = :crypto.hash(:sha256, passage["text"]) |> Base.encode16(case: :lower)

              if passage["checksum"] != checksum or catalog_checksums[passage["id"]] != checksum do
                raise "Catalog checksum differs from normalized reader text for #{passage["id"]}"
              end
            end

            # Revision metadata describes the exact reader bytes, including
            # layout, source-page and annotation changes with unchanged text.
            work =
              work
              |> Map.put(:content_revision, download.checksum)
              |> Map.put(:content_updated_at, content_updated_at)

            write_work!(staging, work, download)
            write!(staging, "api/catalog/#{work.id}/content", download.body)
            {[work | exported], count + 1, bytes + download.byte_size}
          else
            work = Map.drop(work, [:content_revision, :content_updated_at])
            write_work!(staging, work, nil)
            {[work | exported], count, bytes}
          end
        end)

      catalog = %{
        edition: "independent-public-domain",
        content_policy: Catalog.content_policy(),
        audience: "reader",
        works: Enum.reverse(works)
      }

      catalog_body = reader_json!(catalog)
      write!(staging, "api/catalog/index.json", catalog_body)
      write!(staging, "catalog.json", catalog_body)

      File.rename!(staging, destination)

      if bundled_catalog do
        File.mkdir_p!(Path.dirname(bundled_catalog))
        File.write!(bundled_catalog, catalog_body)
      end

      IO.puts(
        "Exported #{length(works)} works and #{download_count} downloads (#{download_bytes} reader bytes) to #{destination}"
      )

      if bundled_catalog, do: IO.puts("Updated bundled catalog: #{bundled_catalog}")
    after
      File.rm_rf(staging)
    end
  end

  defp write_work!(root, work, download) do
    manifest_work =
      Map.take(work, [
        :id,
        :ga_number,
        :title,
        :language,
        :state,
        :proofing_state,
        :content_completeness,
        :content_path,
        :content_revision,
        :content_updated_at
      ])

    bundles =
      if download do
        [
          %{
            id: "#{work.id}-text",
            kind: "json_text_bundle",
            status: "available_on_demand",
            platform: "ios_ipados_macos",
            content_path: work.content_path,
            content_completeness: "complete",
            checksum: download.checksum,
            checksum_algorithm: "sha256",
            byte_size: download.byte_size,
            passages: Enum.map(download.payload["passages"], & &1["id"])
          }
        ]
      else
        []
      end

    manifest = %{
      edition: "independent-public-domain",
      generated_by: "ga_server",
      work: manifest_work,
      content_policy: Catalog.content_policy(),
      bundles: bundles,
      sanity_checks: work.sanity_checks
    }

    write!(root, "api/catalog/#{work.id}/index.json", reader_json!(%{work: work}))
    write!(root, "api/catalog/#{work.id}/manifest", reader_json!(manifest))
  end

  defp content_updated_at do
    root =
      Application.get_env(:ga_server, :catalog_priv_dir) ||
        case :code.priv_dir(:ga_server) do
          {:error, _reason} -> Path.expand("../server/priv", __DIR__)
          path -> to_string(path)
        end

    paths = [
      Path.join(root, "proofreading/catalog.json"),
      Path.join(root, "library/catalog.json")
    ]

    Enum.find_value(paths, fn path ->
      with {:ok, body} <- File.read(path),
           {:ok, %{"generated_at" => timestamp}} when is_binary(timestamp) and timestamp != "" <-
             Jason.decode(body) do
        timestamp
      else
        _ -> nil
      end
    end) ||
      case File.stat(Path.join(root, "library/catalog.json"), time: :posix) do
        {:ok, stat} -> stat.mtime |> DateTime.from_unix!() |> DateTime.to_iso8601()
        _ -> nil
      end
  end

  defp write!(root, relative, body) do
    path = Path.join(root, relative)
    File.mkdir_p!(Path.dirname(path))
    File.write!(path, body)
  end

  defp reader_json!(value) do
    assert_reader_safe!(value)
    Jason.encode!(value)
  end

  defp assert_reader_safe!(map) when is_map(map) do
    if Map.has_key?(map, "source_text") or Map.has_key?(map, :source_text) do
      raise "Refusing to export developer source_text in the public delivery"
    end

    Enum.each(map, fn {_key, value} -> assert_reader_safe!(value) end)
  end

  defp assert_reader_safe!(list) when is_list(list), do: Enum.each(list, &assert_reader_safe!/1)
  defp assert_reader_safe!(_value), do: :ok
end

GA.PublicLibraryExport.run(System.argv())
