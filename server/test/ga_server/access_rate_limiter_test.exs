defmodule GA.Access.RateLimiterTest do
  use ExUnit.Case, async: true

  test "bounds one caller and allows an independent caller" do
    key = {:test, make_ref()}
    assert GA.Access.RateLimiter.allow?(key, 2, 60_000)
    assert GA.Access.RateLimiter.allow?(key, 2, 60_000)
    refute GA.Access.RateLimiter.allow?(key, 2, 60_000)
    assert GA.Access.RateLimiter.allow?({:test, make_ref()}, 2, 60_000)
  end
end
