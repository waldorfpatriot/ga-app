defmodule GA.ContentPipeline do
  @moduledoc """
  Contract for the AI-first source sanity-check workflow.

  The first implementation is intentionally deterministic and side-effect free.
  Later Oban jobs can call these checks after extracting candidate text from
  PDFs, DOC files, OCR XML, and page images.
  """

  @required_checks [
    :source_provenance,
    :original_text_scope,
    :german_diacritics,
    :ocr_artifacts,
    :page_anchor_alignment,
    :dehyphenation,
    :duplicate_paragraphs
  ]
  @page_marker_regex ~r/\[(\d{1,4})\]/u

  def required_checks, do: @required_checks

  def evaluate_candidate(candidate) when is_map(candidate) do
    Enum.map(@required_checks, &run_check(&1, candidate))
  end

  def normalize_content_payload(%{"passages" => passages} = payload) when is_list(passages) do
    metadata =
      payload
      |> Map.get("metadata", %{})
      |> Map.put("page_number_source", page_number_source(passages))

    payload
    |> Map.put("metadata", metadata)
    |> Map.put(
      "passages",
      Enum.map(passages, &normalize_candidate(&1, Map.has_key?(payload, "table_of_contents")))
    )
  end

  def normalize_content_payload(payload), do: payload

  defp page_number_source(passages) do
    sources =
      passages
      |> Enum.flat_map(fn passage ->
        metadata = get_value(passage, :metadata, "metadata", %{})
        anchors = get_value(metadata, :page_anchors, "page_anchors", [])

        if is_list(anchors),
          do: Enum.map(anchors, &get_value(&1, :source, "source", nil)),
          else: []
      end)
      |> Enum.filter(&is_binary/1)
      |> Enum.uniq()

    case sources do
      [] -> "original_inline_bracket_markers"
      [source] -> source
      _ -> "source_page_anchors"
    end
  end

  def normalize_candidate(candidate), do: normalize_candidate(candidate, false)

  def normalize_candidate(candidate, preserve_text) when is_map(candidate) do
    original_text = get_value(candidate, :text, "text", "")

    {text, page_numbers} =
      if preserve_text or has_text_offsets?(candidate),
        do: {original_text, []},
        else: extract_page_markers(original_text)

    candidate
    |> put_value(:text, "text", text)
    |> put_value(
      :checksum,
      "checksum",
      :crypto.hash(:sha256, text) |> Base.encode16(case: :lower)
    )
    |> put_page_number_metadata(page_numbers)
  end

  defp has_text_offsets?(candidate) do
    metadata = get_value(candidate, :metadata, "metadata", %{})
    annotations = get_value(metadata, :annotations, "annotations", [])

    is_map(metadata) and
      (Map.has_key?(metadata, "reading_blocks") or Map.has_key?(metadata, :reading_blocks) or
         Map.has_key?(metadata, "page_anchors") or Map.has_key?(metadata, :page_anchors) or
         (is_list(annotations) and
            Enum.any?(annotations, fn note ->
              is_map(note) and
                Enum.any?(
                  ["start_offset", "end_offset", :start_offset, :end_offset],
                  &Map.has_key?(note, &1)
                )
            end)))
  end

  def extract_page_markers(text) when is_binary(text) do
    page_numbers =
      @page_marker_regex
      |> Regex.scan(text, capture: :all_but_first)
      |> List.flatten()
      |> Enum.map(&String.to_integer/1)
      |> Enum.uniq()

    normalized_text =
      text
      |> then(&Regex.replace(@page_marker_regex, &1, ""))
      |> then(&Regex.replace(~r/[ \t]{2,}/u, &1, " "))
      |> then(&Regex.replace(~r/^[ \t]+|[ \t]+$/mu, &1, ""))
      |> String.trim()

    {normalized_text, page_numbers}
  end

  def extract_page_markers(_text), do: {"", []}

  defp run_check(:source_provenance, candidate) do
    pass_if(
      candidate[:source_id] not in [nil, ""],
      :source_provenance,
      "Candidate has a source id."
    )
  end

  defp run_check(:original_text_scope, candidate) do
    forbidden = [:editorial, :publisher, :introduction, :apparatus, :nachwort, :vorwort_hg]
    flags = Map.get(candidate, :scope_flags, [])
    detected = Enum.filter(flags, &(&1 in forbidden))
    pass_if(detected == [], :original_text_scope, "No protected/editorial scope flags detected.")
  end

  defp run_check(:german_diacritics, candidate) do
    text = Map.get(candidate, :text, "")
    has_german = String.contains?(text, ["ä", "ö", "ü", "Ä", "Ö", "Ü", "ß"])
    pass_if(has_german, :german_diacritics, "German text should preserve umlauts and ß.")
  end

  defp run_check(:ocr_artifacts, candidate) do
    text = Map.get(candidate, :text, "")
    suspicious = Regex.scan(~r/\b(dafi|fiir|Nachlaf|grofi)\b/u, text)
    pass_if(suspicious == [], :ocr_artifacts, "Common OCR artifacts should be absent.")
  end

  defp run_check(:page_anchor_alignment, candidate) do
    pass_if(
      candidate[:ga_page] not in [nil, ""] or source_page_numbers(candidate) != [],
      :page_anchor_alignment,
      "Candidate has source page-number metadata or a GA page anchor."
    )
  end

  defp run_check(:dehyphenation, candidate) do
    text = Map.get(candidate, :text, "")

    pass_if(
      !String.contains?(text, "-\n"),
      :dehyphenation,
      "Line-end hyphenation should be resolved."
    )
  end

  defp run_check(:duplicate_paragraphs, candidate) do
    paragraphs =
      candidate
      |> Map.get(:text, "")
      |> String.split(~r/\n\s*\n/u, trim: true)

    pass_if(
      Enum.uniq(paragraphs) == paragraphs,
      :duplicate_paragraphs,
      "No duplicate paragraphs detected."
    )
  end

  defp pass_if(true, id, detail), do: %{id: id, status: :passed, detail: detail}
  defp pass_if(false, id, detail), do: %{id: id, status: :warning, detail: detail}

  defp source_page_numbers(candidate) do
    candidate
    |> get_value(:metadata, "metadata", %{})
    |> get_value(:page_numbers, "page_numbers", [])
  end

  defp put_page_number_metadata(candidate, []), do: candidate

  defp put_page_number_metadata(candidate, page_numbers) do
    if atom_keyed?(candidate) do
      metadata =
        candidate
        |> Map.get(:metadata, %{})
        |> Map.put(:page_numbers, page_numbers)
        |> Map.put(:page_marker_source, "original_inline_bracket_markers")

      Map.put(candidate, :metadata, metadata)
    else
      metadata =
        candidate
        |> Map.get("metadata", %{})
        |> Map.put("page_numbers", page_numbers)
        |> Map.put("page_marker_source", "original_inline_bracket_markers")

      Map.put(candidate, "metadata", metadata)
    end
  end

  defp get_value(map, atom_key, string_key, default) when is_map(map) do
    Map.get(map, atom_key, Map.get(map, string_key, default))
  end

  defp get_value(_map, _atom_key, _string_key, default), do: default

  defp put_value(map, atom_key, string_key, value) do
    if atom_keyed?(map) do
      Map.put(map, atom_key, value)
    else
      Map.put(map, string_key, value)
    end
  end

  defp atom_keyed?(map) do
    Map.has_key?(map, :text) or Map.has_key?(map, :metadata)
  end
end
