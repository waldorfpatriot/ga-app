defmodule GA.ContentPipelineTest do
  use ExUnit.Case, async: true

  alias GA.ContentPipeline

  test "moves inline source page markers into passage metadata" do
    normalized =
      ContentPipeline.normalize_candidate(%{
        "text" => "[9] Alpha für [10] Beta\n[11] Gamma",
        "metadata" => %{"source" => "doc"}
      })

    assert normalized["metadata"]["page_numbers"] == [9, 10, 11]
    assert normalized["metadata"]["page_marker_source"] == "original_inline_bracket_markers"
    assert normalized["metadata"]["source"] == "doc"
    assert normalized["text"] == "Alpha für Beta\nGamma"

    assert normalized["checksum"] ==
             :crypto.hash(:sha256, normalized["text"]) |> Base.encode16(case: :lower)
  end

  test "refreshes string and atom passage checksums after normalization without changing source text" do
    for candidate <- [
          %{
            "text" => "[15]  Geprüfter Text  ",
            "checksum" => "old",
            "source_text" => "[15] Source copy"
          },
          %{text: "[15]  Geprüfter Text  ", checksum: "old", source_text: "[15] Source copy"}
        ] do
      normalized = ContentPipeline.normalize_candidate(candidate)
      string_keyed = Map.has_key?(candidate, "text")
      text = if string_keyed, do: normalized["text"], else: normalized.text
      checksum = if string_keyed, do: normalized["checksum"], else: normalized.checksum
      source = if string_keyed, do: normalized["source_text"], else: normalized.source_text

      assert text == "Geprüfter Text"
      assert checksum == :crypto.hash(:sha256, text) |> Base.encode16(case: :lower)
      assert source == "[15] Source copy"
      assert ContentPipeline.normalize_candidate(normalized) == normalized
    end
  end

  test "accepts source page-number metadata as page anchor evidence" do
    checks =
      ContentPipeline.evaluate_candidate(%{
        source_id: "rudolf-steiner-ga-003",
        scope_flags: [],
        text: "Mäßig geprüfter Text\n\nohne Duplikate",
        metadata: %{page_numbers: [9]}
      })

    page_anchor_check = Enum.find(checks, &(&1.id == :page_anchor_alignment))
    assert page_anchor_check.status == :passed
  end

  test "canonical offset metadata prevents any further text normalization" do
    text = "  📖 [15] Ein  Vers *\nEine zweite Zeile  "

    for metadata <- [
          %{"reading_blocks" => []},
          %{reading_blocks: []},
          %{"page_anchors" => []},
          %{page_anchors: []},
          %{"annotations" => [%{"start_offset" => 20, "end_offset" => 21}]},
          %{annotations: [%{start_offset: 20, end_offset: 21}]}
        ] do
      normalized = ContentPipeline.normalize_candidate(%{"text" => text, "metadata" => metadata})
      assert normalized["text"] == text
      assert normalized["checksum"] == :crypto.hash(:sha256, text) |> Base.encode16(case: :lower)
    end

    payload = %{"table_of_contents" => [], "passages" => [%{"text" => text}]}
    assert hd(ContentPipeline.normalize_content_payload(payload)["passages"])["text"] == text
  end
end
