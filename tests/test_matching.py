"""Search matching: the title counts most, but the advert text counts too."""

from jobslop.search.matching import match, query_words


def job(title, desc="", tags=()):
    return {"title": title, "desc": desc, "tags": list(tags)}


def run(j, q):
    return match(j, query_words(q), q.lower())


def test_dot_net_stays_one_word():
    assert query_words(".NET developer") == [".net", "developer"]
    assert query_words("C# dev.") == ["c#", "dev"]


def test_found_in_the_advert_when_the_title_is_general():
    m = run(job("Software Developer", "You'll build APIs in C# and ASP.NET Core."), ".net developer")
    assert m["score"] > 0 and not m["title_match"]
    assert "ASP.NET" in m["snippet"]


def test_other_ways_of_writing_it_count():
    assert run(job("Backend Engineer", "Daily work in dotnet as a developer."), ".net developer")["score"] > 0
    assert run(job("Web Dev"), "developer")["score"] > 0
    assert run(job("Senior JavaScript Engineer", "x"), "js")["title_match"]


def test_every_word_must_be_somewhere():
    assert run(job("Java Developer", "Spring Boot and Kafka."), ".net developer")["score"] == 0
    assert run(job("Nurse", "Caring for patients."), "developer")["score"] == 0


def test_title_ranks_above_advert():
    in_title = run(job("Senior .NET Developer", "x"), ".net developer")
    in_advert = run(job("Software Developer", "Work with .NET"), ".net developer")
    assert in_title["title_match"] and in_title["score"] > in_advert["score"]
    assert in_title["snippet"] == ""


def test_title_only_boards_still_work():
    # LinkedIn and Glassdoor give no advert text: most of the words in the title is enough
    assert run(job("Software Developer"), ".net developer")["score"] > 0
    assert run(job("Senior Nurse"), "senior .net developer")["score"] == 0


def test_word_edges():
    assert run(job("Netherlands office manager", "x"), ".net")["score"] == 0
    assert run(job("Developers wanted", "x"), "developer")["title_match"]
    assert run(job("Any title", "x"), "")["score"] == 1
