#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>
#include <chatstyle/style_features.hpp>
#include <string>
#include <vector>

using chatstyle::SparseVector;
using chatstyle::style_features;
using chatstyle::StyleLexicon;
using Catch::Matchers::WithinAbs;

namespace {

constexpr std::size_t kFixedKeys = 15;

double value(const SparseVector& features, const std::u32string& key) {
    return features.at(key);  // at() бросает, если ключа нет
}

SparseVector features_of(const std::vector<std::u32string>& messages,
                         const StyleLexicon& lexicon = {}) {
    return style_features(messages, lexicon);
}

}  // namespace

TEST_CASE("style: empty input gives full key set of zeros", "[style]") {
    StyleLexicon lexicon;
    lexicon.groups = 0;  // только базовые признаки; группы привычек проверяет test_style_habits
    lexicon.function_words = {U"и"};
    lexicon.filler_words = {U"ну"};
    for (const auto& messages :
         {std::vector<std::u32string>{}, std::vector<std::u32string>{U"   ", U""}}) {
        const auto result = style_features(messages, lexicon);
        REQUIRE(result.size() == kFixedKeys + 2);
        for (const auto& entry : result) {
            REQUIRE(entry.second == 0.0);
        }
        REQUIRE(result.count(U"fw:и") == 1);
        REQUIRE(result.count(U"fl:ну") == 1);
    }
}

TEST_CASE("style: runs of closing parentheses", "[style]") {
    const auto r = features_of({U"ну привет)", U"да))", U"ок)))))", U"(см)"});
    REQUIRE_THAT(value(r, U"p:paren1"), WithinAbs(0.5, 1e-12));
    REQUIRE_THAT(value(r, U"p:paren2"), WithinAbs(0.25, 1e-12));
    REQUIRE_THAT(value(r, U"p:paren3+"), WithinAbs(0.25, 1e-12));
}

TEST_CASE("style: ellipsis, exclamation and question runs", "[style]") {
    const auto r = features_of({U"ну...", U"да…", U"что?!", U"ого!!!", U"а??", U".."});
    REQUIRE_THAT(value(r, U"p:ellipsis"), WithinAbs(2.0 / 6, 1e-12));
    REQUIRE_THAT(value(r, U"p:excl1"), WithinAbs(1.0 / 6, 1e-12));
    REQUIRE_THAT(value(r, U"p:excl2+"), WithinAbs(1.0 / 6, 1e-12));
    REQUIRE_THAT(value(r, U"p:quest1"), WithinAbs(1.0 / 6, 1e-12));
    REQUIRE_THAT(value(r, U"p:quest2+"), WithinAbs(1.0 / 6, 1e-12));
    REQUIRE(value(r, U"p:end_dot") == 0.0);
}

TEST_CASE("style: final single dot", "[style]") {
    const auto r = features_of({U"Привет.", U"ну...", U"пока", U"."});
    REQUIRE_THAT(value(r, U"p:end_dot"), WithinAbs(0.5, 1e-12));
}

TEST_CASE("style: share of messages starting with a capital letter", "[style]") {
    // первая буква ищется после цифр; сообщение без букв в знаменатель не входит
    const auto r = features_of({U"Привет", U"привет", U"123 Привет", U"\U0001F600", U"Hello"});
    REQUIRE_THAT(value(r, U"f:capital_start"), WithinAbs(0.75, 1e-12));
}

TEST_CASE("style: yo ratio", "[style]") {
    // ё: 2 («Ёлка», «ёж»), е: 3 («еда», «себе»)
    const auto r = features_of({U"Ёлка ёж", U"еда себе"});
    REQUIRE_THAT(value(r, U"f:yo_ratio"), WithinAbs(0.4, 1e-12));
    REQUIRE(value(features_of({U"привет"}), U"f:yo_ratio") == 0.0);
}

TEST_CASE("style: latin share of letters", "[style]") {
    const auto r = features_of({U"hello мир", U"ок"});
    REQUIRE_THAT(value(r, U"f:latin_share"), WithinAbs(0.5, 1e-12));
}

TEST_CASE("style: emoji per message, skin tone modifier is not counted", "[style]") {
    const auto r = features_of({U"привет \U0001F600\U0001F600", U"ок ❤", U"\U0001F44D\U0001F3FD"});
    REQUIRE_THAT(value(r, U"f:emoji"), WithinAbs(4.0 / 3, 1e-12));
}

TEST_CASE("style: average message length", "[style]") {
    const auto r = features_of({U"привет мир", U"ок"});
    REQUIRE_THAT(value(r, U"r:avg_chars"), WithinAbs(6.0, 1e-12));
    REQUIRE_THAT(value(r, U"r:avg_words"), WithinAbs(1.5, 1e-12));
}

TEST_CASE("style: word frequencies with a hyphenated word", "[style]") {
    StyleLexicon lexicon;
    lexicon.function_words = {U"и", U"что", U"то"};
    lexicon.filler_words = {U"ну", U"типа"};
    // слова: ну, что-то, и, то | ну, и  -> всего 6; «что» внутри «что-то» не считается
    const auto r = features_of({U"Ну, что-то и то", U"ну и"}, lexicon);
    REQUIRE_THAT(value(r, U"fw:и"), WithinAbs(2.0 / 6, 1e-12));
    REQUIRE_THAT(value(r, U"fw:то"), WithinAbs(1.0 / 6, 1e-12));
    REQUIRE(value(r, U"fw:что") == 0.0);
    REQUIRE_THAT(value(r, U"fl:ну"), WithinAbs(2.0 / 6, 1e-12));
    REQUIRE(value(r, U"fl:типа") == 0.0);
}

TEST_CASE("style: hyphen rules for words", "[style]") {
    // «из-за» одно слово, одиночный дефис и «а-» с хвостовым дефисом слов не склеивают
    const auto r = features_of({U"из-за - привет а-"});
    REQUIRE_THAT(value(r, U"r:avg_words"), WithinAbs(3.0, 1e-12));
}

TEST_CASE("style: lexicon words are lowercased and deduplicated", "[style]") {
    StyleLexicon lexicon;
    lexicon.groups = 0;
    lexicon.function_words = {U"И", U"и"};
    lexicon.filler_words = {U"Ну"};
    const auto r = features_of({U"ну и"}, lexicon);
    REQUIRE(r.size() == kFixedKeys + 2);
    REQUIRE_THAT(value(r, U"fl:ну"), WithinAbs(0.5, 1e-12));
    REQUIRE_THAT(value(r, U"fw:и"), WithinAbs(0.5, 1e-12));
}

TEST_CASE("style: ignored tokens do not affect features", "[style]") {
    StyleLexicon lexicon;
    lexicon.ignored_tokens = {U"<URL>", U"<MENTION>"};
    const std::vector<std::u32string> messages = {U"<URL>", U"<MENTION> привет", U"смотри <URL>"};
    const auto r = features_of(messages, lexicon);
    // первое сообщение после удаления метки пусто и пропущено
    REQUIRE_THAT(value(r, U"r:avg_chars"), WithinAbs(6.0, 1e-12));
    REQUIRE_THAT(value(r, U"r:avg_words"), WithinAbs(1.0, 1e-12));
    REQUIRE(value(r, U"f:latin_share") == 0.0);
    REQUIRE(value(r, U"f:capital_start") == 0.0);
    // без списка меток буквы «URL» и «MENTION» попали бы в латиницу и заглавные
    const auto plain = features_of(messages);
    REQUIRE(value(plain, U"f:latin_share") > 0.0);
    REQUIRE(value(plain, U"f:capital_start") > 0.0);
}

TEST_CASE("style: result is deterministic", "[style]") {
    StyleLexicon lexicon;
    lexicon.function_words = {U"и", U"не"};
    const std::vector<std::u32string> messages = {U"Ну привет)) и пока...", U"Не знаю!"};
    REQUIRE(style_features(messages, lexicon) == style_features(messages, lexicon));
}
