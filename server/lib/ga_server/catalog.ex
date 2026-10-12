defmodule GA.Catalog do
  @moduledoc """
  Public catalog and content-manifest data for the independent edition.

  User-private reading state, bookmarks, notes, and highlights belong in
  CloudKit/iCloud. This context only exposes public library data and source
  quality state that Apple clients can cache.
  """

  alias GA.ContentPipeline

  @edition "independent-public-domain"
  @reviewed_work_ids ~w(ga-003 ga-004 ga-009 ga-010 ga-013)
  @content_policy %{
    author_scope: "rudolf_steiner_original_text_only",
    languages: "original_languages_only",
    complete_volumes_only: true,
    excludes: [
      "publisher_pages",
      "modern_editorial_notes",
      "introductions_by_other_authors",
      "protected_apparatus"
    ],
    user_sync: "cloudkit_private_database"
  }

  def content_policy, do: @content_policy

  def list_works(params \\ %{}), do: list_reader_works(params)

  def list_reader_works(params \\ %{}) do
    complete_works()
    |> filter(params)
    |> Enum.sort_by(&ga_sort_key/1)
  end

  def list_developer_works(params \\ %{}) do
    complete_works()
    |> filter(params)
    |> Enum.sort_by(&ga_sort_key/1)
  end

  def get_work(id), do: get_developer_work(id)

  def get_reader_work(id), do: Enum.find(list_reader_works(), &(&1.id == id))

  def get_developer_work(id), do: Enum.find(complete_works(), &(&1.id == id))

  def manifest(id) do
    with work when not is_nil(work) <- get_reader_work(id) do
      download = download(id)

      manifest_work =
        Map.take(work, [
          :id,
          :ga_number,
          :title,
          :language,
          :state,
          :proofing_state,
          :content_completeness,
          :content_path
        ])

      %{
        edition: @edition,
        generated_by: "ga_server",
        work:
          if(download,
            do: manifest_work,
            else:
              manifest_work
              |> Map.delete(:content_path)
              |> Map.put(:content_completeness, "unavailable")
          ),
        content_policy: @content_policy,
        bundles: bundles_for(work, download),
        sanity_checks: work.sanity_checks
      }
    end
  end

  def content(id) do
    with payload when not is_nil(payload) <- proofing_content(id) do
      without_source_text(payload)
    end
  end

  @doc "The exact reader JSON bytes, with integrity metadata for an offline download."
  def download(id) do
    with payload when not is_nil(payload) <- content(id) do
      body = Jason.encode!(payload)

      %{
        body: body,
        payload: payload,
        byte_size: byte_size(body),
        checksum: :crypto.hash(:sha256, body) |> Base.encode16(case: :lower)
      }
    end
  end

  def proofing_content(id) do
    with true <- valid_id?(id),
         %{content_path: content_path, content_completeness: "complete", state: state} =
           work
         when is_binary(content_path) and state != "published_seed" <- get_reader_work(id),
         {:ok, body} <- read_content_file(content_file(id)),
         {:ok, payload} <- Jason.decode(body),
         true <- valid_payload?(payload, id),
         true <- catalog_payload_matches?(work, payload) do
      payload
      |> ContentPipeline.normalize_content_payload()
      |> Map.put("passage_count", length(payload["passages"]))
      |> Map.put("content_completeness", "complete")
      |> Map.put("content_path", content_path)
    else
      _ -> nil
    end
  end

  defp valid_id?(id) when is_binary(id), do: Regex.match?(~r/\Aga-[a-z0-9]+(?:-[a-z0-9]+)*\z/, id)
  defp valid_id?(_id), do: false

  defp valid_payload?(%{"work_id" => id, "passages" => passages} = payload, id)
       when is_list(passages) and passages != [] do
    complete_payload?(payload, id) and
      is_map(Map.get(payload, "metadata", %{})) and
      Map.get(payload, "passage_count", length(passages)) == length(passages) and
      Enum.all?(passages, fn
        %{"id" => passage_id, "title" => title, "source_label" => source_label, "text" => text} =
            passage
        when is_binary(passage_id) and is_binary(title) and is_binary(source_label) and
               is_binary(text) ->
          passage_id != "" and String.trim(text) != "" and
            (is_nil(passage["ga_page"]) or is_binary(passage["ga_page"])) and
            valid_passage_metadata?(Map.get(passage, "metadata", %{}), text, passage)

        _ ->
          false
      end) and
      length(Enum.uniq_by(passages, & &1["id"])) == length(passages) and
      valid_reading_section_ids?(passages) and
      valid_table_of_contents?(Map.get(payload, "table_of_contents", []), passages)
  end

  defp valid_payload?(_payload, _id), do: false

  defp catalog_payload_matches?(work, payload) do
    passages = payload["passages"]

    Map.get(work, :catalog_passage_count, length(work.passages)) == length(passages) and
      Enum.map(work.passages, & &1.id) == Enum.map(passages, & &1["id"])
  end

  defp complete_payload?(payload, id) do
    legacy_default = if id in @reviewed_work_ids, do: "complete", else: "unavailable"

    completeness =
      Map.get(payload, "content_completeness", Map.get(payload, "completeness", legacy_default))

    completeness == "complete" and payload["state"] != "published_seed" and
      Enum.all?(["content_completeness", "completeness"], fn key ->
        not Map.has_key?(payload, key) or payload[key] == "complete"
      end)
  end

  defp valid_passage_metadata?(metadata, text, passage) when is_map(metadata) do
    page_numbers = Map.get(metadata, "page_numbers", [])
    annotations = Map.get(metadata, "annotations", [])

    is_list(page_numbers) and Enum.all?(page_numbers, &is_integer/1) and
      (is_nil(metadata["page_marker_source"]) or is_binary(metadata["page_marker_source"])) and
      is_list(annotations) and
      (not Map.has_key?(metadata, "group_title") or is_binary(metadata["group_title"])) and
      valid_reading_metadata?(metadata, text, passage)
  end

  defp valid_passage_metadata?(_metadata, _text, _passage), do: false

  defp valid_reading_metadata?(metadata, text, passage) do
    annotations = Map.get(metadata, "annotations", [])

    uses_offsets =
      Map.has_key?(metadata, "reading_blocks") or Map.has_key?(metadata, "reading_sections") or
        Map.has_key?(metadata, "page_anchors") or
        Enum.any?(annotations, fn note ->
          is_map(note) and
            (Map.has_key?(note, "start_offset") or Map.has_key?(note, "end_offset"))
        end)

    context = if uses_offsets, do: utf16_context(text)

    valid_reading_blocks?(Map.get(metadata, "reading_blocks", []), context) and
      valid_reading_sections?(metadata, context, passage) and
      valid_page_anchors?(Map.get(metadata, "page_anchors", []), context) and
      Enum.all?(annotations, &valid_source_annotation?(&1, context))
  end

  defp valid_reading_blocks?([], _context), do: true

  defp valid_reading_blocks?(blocks, context) when is_list(blocks) and is_map(context) do
    result =
      Enum.reduce_while(blocks, {:ok, 0}, fn
        %{"kind" => kind, "start_offset" => start, "end_offset" => finish} = block,
        {:ok, previous_end} ->
          if kind in ~w(heading verse prose attribution note) and
               valid_utf16_range?(start, finish, context) and start >= previous_end and
               String.trim(utf16_slice(context, previous_end, start)) == "" and
               (not Map.has_key?(block, "level") or
                  (is_integer(block["level"]) and block["level"] in 1..6)) and
               (not Map.has_key?(block, "poem_start") or is_boolean(block["poem_start"])) do
            {:cont, {:ok, finish}}
          else
            {:halt, :invalid}
          end

        _, _ ->
          {:halt, :invalid}
      end)

    case result do
      {:ok, finish} -> String.trim(utf16_slice(context, finish, context.length)) == ""
      _ -> false
    end
  end

  defp valid_reading_blocks?(_blocks, _context), do: false

  defp valid_reading_sections?(metadata, context, passage) do
    case Map.fetch(metadata, "reading_sections") do
      :error ->
        true

      {:ok, sections} when is_list(sections) and sections != [] and is_map(context) ->
        blocks = Map.get(metadata, "reading_blocks", [])
        starts = MapSet.new(blocks, & &1["start_offset"])
        ends = MapSet.new(blocks, & &1["end_offset"])

        result =
          sections
          |> Enum.with_index()
          |> Enum.reduce_while({:ok, 0}, fn
            {%{
               "id" => id,
               "title" => title,
               "label_kind" => kind,
               "start_offset" => start,
               "end_offset" => finish
             }, index},
            {:ok, previous} ->
              expected_id =
                if index == 0,
                  do: passage["id"],
                  else: passage["id"] <> "-section-" <> Integer.to_string(index + 1)

              if id == expected_id and is_binary(title) and String.trim(title) != "" and
                   kind in ~w(source_title incipit) and valid_utf16_range?(start, finish, context) and
                   start >= previous and MapSet.member?(starts, start) and
                   MapSet.member?(ends, finish) and
                   String.trim(utf16_slice(context, previous, start)) == "" and
                   valid_section_label?(
                     kind,
                     title,
                     index,
                     start,
                     finish,
                     blocks,
                     context,
                     passage
                   ) do
                {:cont, {:ok, finish}}
              else
                {:halt, :invalid}
              end

            _, _ ->
              {:halt, :invalid}
          end)

        case result do
          {:ok, finish} -> String.trim(utf16_slice(context, finish, context.length)) == ""
          _ -> false
        end

      _ ->
        false
    end
  end

  defp valid_section_label?("incipit", title, _index, start, finish, blocks, context, _passage) do
    case Enum.find(blocks, &(&1["start_offset"] == start and &1["end_offset"] <= finish)) do
      %{"kind" => "verse"} = verse ->
        utf16_slice(context, start, verse["end_offset"])
        |> String.split("\n", parts: 2)
        |> hd() == title

      _ ->
        false
    end
  end

  defp valid_section_label?("source_title", title, index, start, finish, blocks, context, passage) do
    (index == 0 and start == 0 and title == passage["title"]) or
      case Enum.find(blocks, &(&1["start_offset"] == start and &1["end_offset"] <= finish)) do
        %{"kind" => "heading"} = heading ->
          utf16_slice(context, start, heading["end_offset"])
          |> String.split("\n", parts: 2)
          |> hd() == title

        _ ->
          false
      end
  end

  defp valid_reading_section_ids?(passages) do
    passage_ids = MapSet.new(passages, & &1["id"])

    sections =
      Enum.flat_map(passages, fn passage ->
        for section <- Map.get(passage["metadata"] || %{}, "reading_sections", []),
            do: {section["id"], passage["id"]}
      end)

    length(Enum.uniq_by(sections, &elem(&1, 0))) == length(sections) and
      Enum.all?(sections, fn {id, owner} -> not MapSet.member?(passage_ids, id) or id == owner end)
  end

  defp valid_page_anchors?([], _context), do: true

  defp valid_page_anchors?(anchors, context) when is_list(anchors) and is_map(context) do
    Enum.reduce_while(anchors, 0, fn
      %{"page" => page, "start_offset" => start, "source" => source} = anchor, previous ->
        if is_integer(page) and page > 0 and is_binary(source) and
             valid_utf16_offset?(start, context) and start >= previous and
             (not Map.has_key?(anchor, "confidence") or is_binary(anchor["confidence"])) and
             (not Map.has_key?(anchor, "source_section") or
                (is_integer(anchor["source_section"]) and anchor["source_section"] >= 0)),
           do: {:cont, start},
           else: {:halt, :invalid}

      _, _ ->
        {:halt, :invalid}
    end) != :invalid
  end

  defp valid_page_anchors?(_anchors, _context), do: false

  defp valid_source_annotation?(%{"id" => id, "marker" => marker, "text" => text} = note, context)
       when is_binary(id) and is_binary(marker) and is_binary(text) do
    if Map.has_key?(note, "start_offset") or Map.has_key?(note, "end_offset") do
      start = note["start_offset"]
      finish = note["end_offset"]
      valid_utf16_range?(start, finish, context) and utf16_slice(context, start, finish) == marker
    else
      true
    end
  end

  defp valid_source_annotation?(_note, _context), do: false

  defp valid_table_of_contents?([], _passages), do: true

  defp valid_table_of_contents?(entries, passages) when is_list(entries) do
    contexts = Map.new(passages, &{&1["id"], utf16_context(&1["text"])})
    nodes = Map.new(Enum.filter(entries, &is_map/1), &{&1["id"], &1})

    map_size(nodes) == length(entries) and
      Enum.all?(entries, fn
        %{
          "id" => id,
          "title" => title,
          "level" => level,
          "passage_id" => passage_id,
          "start_offset" => offset,
          "parent_id" => parent_id
        } ->
          parent = nodes[parent_id]

          is_binary(id) and id != "" and is_binary(title) and String.trim(title) != "" and
            is_integer(level) and level in 1..6 and
            valid_utf16_offset?(offset, contexts[passage_id]) and
            (is_nil(parent_id) or
               (is_binary(parent_id) and is_map(parent) and is_integer(parent["level"]) and
                  parent["level"] < level))

        _ ->
          false
      end)
  end

  defp valid_table_of_contents?(_entries, _passages), do: false

  defp utf16_context(text) do
    {length, boundaries} =
      text
      |> String.to_charlist()
      |> Enum.reduce({0, MapSet.new([0])}, fn point, {offset, boundaries} ->
        next = offset + if(point > 0xFFFF, do: 2, else: 1)
        {next, MapSet.put(boundaries, next)}
      end)

    %{
      length: length,
      boundaries: boundaries,
      bytes: :unicode.characters_to_binary(text, :utf8, {:utf16, :little})
    }
  end

  defp valid_utf16_offset?(offset, %{length: length, boundaries: boundaries}) do
    is_integer(offset) and offset >= 0 and offset <= length and MapSet.member?(boundaries, offset)
  end

  defp valid_utf16_offset?(_offset, _context), do: false

  defp valid_utf16_range?(start, finish, context) do
    valid_utf16_offset?(start, context) and valid_utf16_offset?(finish, context) and
      finish > start
  end

  defp utf16_slice(%{bytes: bytes}, start, finish) do
    bytes
    |> binary_part(start * 2, (finish - start) * 2)
    |> :unicode.characters_to_binary({:utf16, :little}, :utf8)
  end

  defp without_source_text(map) when is_map(map) do
    map
    |> Map.delete("source_text")
    |> Map.new(fn {key, value} -> {key, without_source_text(value)} end)
  end

  defp without_source_text(list) when is_list(list), do: Enum.map(list, &without_source_text/1)
  defp without_source_text(value), do: value

  defp filter(works, params) do
    works
    |> filter_query(params)
    |> filter_state(params)
  end

  defp filter_query(works, %{"q" => query}) when byte_size(query) > 0 do
    normalized = String.downcase(query)

    Enum.filter(works, fn work ->
      searchable =
        [
          work.ga_number,
          work.title,
          work.subtitle,
          work.language,
          work.type,
          work.state,
          work.proofing_state | work.tags
        ]
        |> Enum.reject(&is_nil/1)
        |> Enum.join(" ")
        |> String.downcase()

      String.contains?(searchable, normalized)
    end)
  end

  defp filter_query(works, _params), do: works

  defp filter_state(works, %{"state" => state}) when byte_size(state) > 0 do
    Enum.filter(works, &(&1.state == state))
  end

  defp filter_state(works, _params), do: works

  defp complete_works do
    bundled_by_id = Map.new(bundled_works(), &{&1.id, &1})
    curated_by_id = Map.new(curated_works(), &{&1.id, &1})

    # Preserve the reviewed books, while complete imports replace seed excerpts
    # and queued rows. The release contains all metadata under priv/library.
    Map.merge(curated_by_id, bundled_by_id, fn id, curated, bundled ->
      if id in @reviewed_work_ids, do: curated, else: bundled
    end)
    |> Map.values()
  end

  defp bundled_works do
    cached_metadata(priv_file(["library", "catalog.json"]), fn path ->
      load_bundled_works(path)
    end)
  end

  defp load_bundled_works(path) do
    with {:ok, body} <- File.read(path),
         {:ok, %{"works" => works}} when is_list(works) <- Jason.decode(body) do
      works
      |> Enum.map(&bundled_work/1)
      |> Enum.reject(&is_nil/1)
    else
      _ -> []
    end
  end

  defp bundled_work(%{"id" => id} = work) do
    if valid_id?(id) and valid_work_metadata?(work) do
      defaults = %{
        id: id,
        ga_number: "GA " <> String.replace_prefix(id, "ga-", ""),
        title: id,
        subtitle: "",
        language: "de",
        year_label: "",
        type: "lectures",
        priority: ga_priority(id),
        state: "import_queue",
        proofing_state: "source_pending",
        tags: [],
        source_summary: "",
        content_completeness: "unavailable",
        sanity_checks: [],
        passages: []
      }

      metadata =
        Map.new(defaults, fn {key, default} ->
          {key, Map.get(work, Atom.to_string(key), default)}
        end)
        |> Map.put(
          :sanity_checks,
          Enum.map(Map.get(work, "sanity_checks", []), &check_metadata/1)
        )
        |> Map.put(:passages, Enum.map(Map.get(work, "passages", []), &passage_metadata/1))
        |> Map.put(
          :content_completeness,
          if(
            work["content_completeness"] == "complete" and
              Map.get(work, "completeness", "complete") == "complete" and
              work["state"] != "published_seed",
            do: "complete",
            else: "unavailable"
          )
        )
        |> Map.put(
          :catalog_passage_count,
          Map.get(work, "catalog_passage_count", length(Map.get(work, "passages", [])))
        )

      if metadata.content_completeness == "complete" and metadata.state != "published_seed" and
           Map.get(work, "completeness", "complete") == "complete" and
           work["content_path"] == "/api/catalog/#{id}/content",
         do: Map.put(metadata, :content_path, work["content_path"]),
         else: metadata
    end
  end

  defp bundled_work(_work), do: nil

  defp valid_work_metadata?(work) do
    Enum.all?(
      ~w(ga_number title subtitle language year_label type state proofing_state source_summary content_completeness),
      fn key ->
        not Map.has_key?(work, key) or is_binary(work[key])
      end
    ) and
      is_list(Map.get(work, "tags", [])) and
      Enum.all?(Map.get(work, "tags", []), &is_binary/1) and
      is_list(Map.get(work, "sanity_checks", [])) and
      Enum.all?(Map.get(work, "sanity_checks", []), &is_map/1) and
      is_list(Map.get(work, "passages", [])) and
      Enum.all?(Map.get(work, "passages", []), &is_map/1)
  end

  defp check_metadata(check) do
    Map.new([:id, :title, :status, :detail], &{&1, Map.get(check, Atom.to_string(&1))})
  end

  defp passage_metadata(passage) do
    Map.new(
      [:id, :title, :ga_page, :source_label, :checksum],
      &{&1, Map.get(passage, Atom.to_string(&1))}
    )
  end

  defp ga_sort_key(work), do: {ga_priority(work.id), work.id}

  defp ga_priority("ga-" <> suffix) do
    case Regex.run(~r/\A(\d+)([a-z]*)(?:-(\d+))?/i, suffix) do
      [_, number, alpha_suffix] ->
        String.to_integer(number) * 100 + alpha_suffix_offset(alpha_suffix)

      [_, number, alpha_suffix, part] ->
        String.to_integer(number) * 100 + alpha_suffix_offset(alpha_suffix) +
          String.to_integer(part)

      _ ->
        999_999
    end
  end

  defp ga_priority(_id), do: 999_999

  defp alpha_suffix_offset(""), do: 0

  defp alpha_suffix_offset(suffix) do
    suffix
    |> String.downcase()
    |> String.to_charlist()
    |> Enum.reduce(0, fn char, acc -> acc * 26 + char - ?a + 1 end)
  end

  defp bundles_for(work, %{payload: payload, checksum: checksum, byte_size: byte_size}) do
    [
      %{
        id: "#{work.id}-text",
        kind: "json_text_bundle",
        status: "available_on_demand",
        platform: "ios_ipados_macos",
        content_path: work.content_path,
        content_completeness: "complete",
        checksum: checksum,
        checksum_algorithm: "sha256",
        byte_size: byte_size,
        passages: Enum.map(payload["passages"], & &1["id"])
      }
    ]
  end

  defp bundles_for(_work, nil), do: []

  defp content_file(id) do
    json = priv_file(["content", "#{id}.json"])
    gzip = json <> ".gz"

    if id not in @reviewed_work_ids and File.regular?(gzip),
      do: gzip,
      else: json
  end

  defp read_content_file(path) do
    with {:ok, body} <- File.read(path) do
      if String.ends_with?(path, ".gz"), do: {:ok, :zlib.gunzip(body)}, else: {:ok, body}
    end
  rescue
    _ in [ErlangError, ArgumentError] -> {:error, :invalid_compression}
  end

  defp priv_file(parts) do
    case Application.get_env(:ga_server, :catalog_priv_dir) do
      path when is_binary(path) ->
        Path.join([path | parts])

      _ ->
        case :code.priv_dir(:ga_server) do
          {:error, _reason} -> Path.join([Path.expand("../../priv", __DIR__) | parts])
          priv_dir -> Path.join([to_string(priv_dir) | parts])
        end
    end
  end

  defp content_passages(id) do
    cached_metadata(content_file(id), &load_content_passages/1)
  end

  # Only metadata is cached. Downloads are read and validated on demand, so a
  # missing or damaged file never keeps an old "available" manifest alive.
  defp cached_metadata(path, loader) do
    signature =
      case File.stat(path) do
        {:ok, stat} -> {stat.mtime, stat.ctime, stat.size, stat.inode}
        {:error, reason} -> {:missing, reason}
      end

    key = {__MODULE__, :metadata, path}

    case :persistent_term.get(key, nil) do
      {^signature, value} ->
        value

      _ ->
        value = loader.(path)
        :persistent_term.put(key, {signature, value})
        value
    end
  end

  defp load_content_passages(path) do
    with {:ok, body} <- read_content_file(path),
         {:ok, %{"passages" => passages}} when is_list(passages) <- Jason.decode(body) do
      passages |> Enum.filter(&is_map/1) |> Enum.map(&passage_metadata/1)
    else
      _ -> []
    end
  end

  defp queued_check(id, title, detail), do: check(id, title, "queued", detail)
  defp passed_check(id, title, detail), do: check(id, title, "passed", detail)
  defp warning_check(id, title, detail), do: check(id, title, "warning", detail)

  defp check(id, title, status, detail) do
    %{id: id, title: title, status: status, detail: detail}
  end

  defp curated_works do
    [
      %{
        id: "ga-004",
        ga_number: "GA 004",
        title: "Die Philosophie der Freiheit",
        subtitle: "Grundzüge einer modernen Weltanschauung",
        language: "de",
        year_label: "1894",
        type: "book",
        priority: 1,
        state: "published",
        proofing_state: "ai_checked",
        tags: ["freedom", "philosophy", "ethics", "core"],
        content_path: "/api/catalog/ga-004/content",
        source_summary:
          "Complete public-domain DOC source normalized into 18 auditable sections. The original source text is retained for developer diff review.",
        sanity_checks: [
          passed_check(
            "source",
            "Source acquisition",
            "Internet Archive Public Domain Mark source retained with provenance."
          ),
          passed_check(
            "scope",
            "Original-text isolation",
            "Archive header and table of contents are excluded from the reader text."
          ),
          passed_check(
            "ocr",
            "OCR sanity pass",
            "German diacritics, Word fields and common OCR artifacts passed automated checks."
          )
        ],
        passages: content_passages("ga-004")
      },
      %{
        id: "ga-010",
        ga_number: "GA 010",
        title: "Wie erlangt man Erkenntnisse der höheren Welten?",
        subtitle: "Core spiritual-scientific work",
        language: "de",
        year_label: "1904-1905",
        type: "book",
        priority: 2,
        state: "published",
        proofing_state: "ai_checked",
        tags: ["core", "training", "meditation"],
        content_path: "/api/catalog/ga-010/content",
        source_summary:
          "Complete public-domain DOC source normalized into 16 auditable sections. The original source text is retained for developer diff review.",
        sanity_checks: [
          passed_check(
            "source",
            "Source acquisition",
            "Internet Archive Public Domain Mark source retained with provenance."
          ),
          passed_check(
            "scope",
            "Original-text isolation",
            "Archive header and table of contents are excluded from the reader text."
          ),
          passed_check(
            "ocr",
            "OCR sanity pass",
            "German diacritics, Word fields and common OCR artifacts passed automated checks."
          )
        ],
        passages: content_passages("ga-010")
      },
      %{
        id: "ga-013",
        ga_number: "GA 013",
        title: "Die Geheimwissenschaft im Umriß",
        subtitle: "Large structured book with terminology-heavy passages",
        language: "de",
        year_label: "1910",
        type: "book",
        priority: 3,
        state: "published",
        proofing_state: "ai_checked",
        tags: ["core", "cosmology", "anthroposophy"],
        content_path: "/api/catalog/ga-013/content",
        source_summary:
          "Complete public-domain DOC source normalized into 17 auditable sections. The original source text is retained for developer diff review.",
        sanity_checks: [
          passed_check(
            "source",
            "Source acquisition",
            "Internet Archive Public Domain Mark source retained with provenance."
          ),
          passed_check(
            "scope",
            "Original-text isolation",
            "Archive header and table of contents are excluded from the reader text."
          ),
          passed_check(
            "ocr",
            "OCR sanity pass",
            "German diacritics, Word fields and common OCR artifacts passed automated checks."
          )
        ],
        passages: content_passages("ga-013")
      },
      %{
        id: "ga-009",
        ga_number: "GA 009",
        title: "Theosophie",
        subtitle: "Einführung in übersinnliche Welterkenntnis und Menschenbestimmung",
        language: "de",
        year_label: "1904",
        type: "book",
        priority: 4,
        state: "published",
        proofing_state: "ai_checked",
        tags: ["core", "introduction", "anthroposophy"],
        content_path: "/api/catalog/ga-009/content",
        source_summary:
          "Complete public-domain DOC source normalized into 16 auditable sections. Publisher-only notes are excluded; original source text is retained for developer diff review.",
        sanity_checks: [
          passed_check(
            "source",
            "Source acquisition",
            "Internet Archive Public Domain Mark source retained with provenance."
          ),
          passed_check(
            "scope",
            "Original-text isolation",
            "Archive header, contents and publisher notes are excluded from reader text."
          ),
          passed_check(
            "ocr",
            "OCR sanity pass",
            "German diacritics, Word fields and common OCR artifacts passed automated checks."
          )
        ],
        passages: content_passages("ga-009")
      },
      %{
        id: "ga-003",
        ga_number: "GA 003",
        title: "Wahrheit und Wissenschaft",
        subtitle: "Vorspiel zu einer Philosophie der Freiheit",
        language: "de",
        year_label: "1892",
        type: "book",
        priority: 5,
        state: "published",
        proofing_state: "ai_checked",
        tags: ["philosophy", "knowledge", "freedom"],
        content_path: "/api/catalog/ga-003/content",
        source_summary:
          "Complete public-domain DOC source normalized into 10 auditable sections. Archive front matter and Word fields are excluded; original source text is retained for developer diff review.",
        sanity_checks: [
          passed_check(
            "content",
            "Complete text payload",
            "Server payload contains 10 passages."
          ),
          passed_check("umlauts", "German diacritics", "Candidate text preserves ä, ö, ü and ß."),
          passed_check(
            "scope",
            "Original text scope",
            "Source header, table of contents and trailing Word field were excluded from the content endpoint."
          ),
          passed_check(
            "proofing",
            "Full-volume proofing",
            "Automated normalization and production sanity checks pass; every change remains available in the developer diff."
          )
        ],
        passages: content_passages("ga-003")
      },
      %{
        id: "ga-120",
        ga_number: "GA 120",
        title: "Die Offenbarungen des Karma",
        subtitle: "Elf Vorträge, Hamburg, 16.-28. Mai 1910",
        language: "de",
        year_label: "1910",
        type: "lecture_cycle",
        priority: 6,
        state: "import_queue",
        proofing_state: "source_pending",
        content_completeness: "unavailable",
        tags: ["karma", "lectures", "hamburg"],
        source_summary:
          "The complete cycle of eleven lectures is required before this volume can be downloaded.",
        sanity_checks: [
          queued_check(
            "complete-volume",
            "Complete volume",
            "The full eleven-lecture cycle is required."
          ),
          queued_check(
            "scope",
            "Original text scope",
            "Original-text scope remains under review."
          )
        ],
        passages: []
      }
      |> complete_ga_120_fallback(),
      %{
        id: "ga-293",
        ga_number: "GA 293",
        title: "Allgemeine Menschenkunde als Grundlage der Pädagogik",
        subtitle: "Education priority volume for Waldorf-related readers",
        language: "de",
        year_label: "1919",
        type: "education",
        priority: 7,
        state: "import_queue",
        proofing_state: "source_pending",
        tags: ["education", "waldorf", "pedagogy"],
        source_summary:
          "Important/popular education volume. Source import and AI sanity checks are queued.",
        sanity_checks: [
          queued_check("source", "Source acquisition", "Source discovery pending"),
          queued_check(
            "scope",
            "Original-text isolation",
            "Exclude publisher pages, introductions, editorial notes and apparatus."
          ),
          queued_check(
            "ocr",
            "OCR sanity pass",
            "Compare PDF text, DOC text and page-image OCR before publication."
          )
        ],
        passages: []
      }
    ]
    |> Enum.map(fn work ->
      Map.put_new(
        work,
        :content_completeness,
        if(work.id in @reviewed_work_ids, do: "complete", else: "unavailable")
      )
    end)
  end

  defp complete_ga_120_fallback(work) do
    path = priv_file(["content", "ga-120.json.gz"])

    case cached_metadata(path, &complete_ga_120_metadata/1) do
      [] ->
        work

      passages ->
        work
        |> Map.put(:state, "sanity_check")
        |> Map.put(:proofing_state, "needs_ai_sanity_check")
        |> Map.put(:content_completeness, "complete")
        |> Map.put(:content_path, "/api/catalog/ga-120/content")
        |> Map.put(:catalog_passage_count, 11)
        |> Map.put(:passages, passages)
        |> Map.put(
          :source_summary,
          "The complete eleven-lecture cycle is installed. Original-text scope remains under review."
        )
        |> Map.put(:sanity_checks, [
          passed_check("complete-volume", "Complete volume", "All eleven lectures are present."),
          warning_check(
            "scope",
            "Original text scope",
            "Original-text scope remains under review."
          )
        ])
    end
  end

  defp complete_ga_120_metadata(path) do
    with {:ok, body} <- read_content_file(path),
         {:ok, %{"passages" => passages} = payload} when length(passages) == 11 <-
           Jason.decode(body),
         true <- valid_payload?(payload, "ga-120") do
      Enum.map(passages, &(&1 |> ContentPipeline.normalize_candidate() |> passage_metadata()))
    else
      _ -> []
    end
  end
end
