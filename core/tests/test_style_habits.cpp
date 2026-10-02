#include <catch2/catch_test_macros.hpp>
#include <catch2/matchers/catch_matchers_floating_point.hpp>
#include <chatstyle/style_features.hpp>
#include <cmath>
#include <string>
#include <vector>

using chatstyle::SparseVector;
using chatstyle::style_features;
using chatstyle::StyleLexicon;
using chatstyle::kGroupPunctuation;
using chatstyle::kGroupOrthography;
using chatstyle::kGroupWords;
using chatstyle::kGroupSentences;
using chatstyle::kGroupAll;
using Catch::Matchers::WithinAbs;

namespace {

double value(const SparseVector& features, const std::u32string& key) {
    return features.at(key);  // at() бросает, если ключа нет
}

SparseVector features_of(const std::vector<std::u32string>& messages,
                         unsigned groups,
                         const StyleLexicon& lexicon = {}) {
    StyleLexicon lex = lexicon;
    lex.groups = groups;
    return style_features(messages, lex);
}

}  // namespace

TEST_CASE("style: comma_per_word and comma_before_conj", "[habits]") {
    StyleLexicon lexicon;
    lexicon.conjunctions = {U"что", U"но"};
    const auto r = features_of({U"привет, как дела", U"да, но нет"}, kGroupPunctuation, lexicon);
    REQUIRE_THAT(value(r, U"p:comma_per_word"), WithinAbs(2.0 / 6, 1e-12));
    REQUIRE_THAT(value(r, U"p:comma_before_conj"), WithinAbs(1.0, 1e-12));
}

TEST_CASE("style: comma_before_conj with mixed cases", "[habits]") {
    StyleLexicon lexicon;
    lexicon.conjunctions = {U"что", U"но"};
    const auto r = features_of({U"я думаю, что да", U"ну но нет"}, kGroupPunctuation, lexicon);
    REQUIRE_THAT(value(r, U"p:comma_before_conj"), WithinAbs(0.5, 1e-12));
}

TEST_CASE("style: conjunction at start not counted", "[habits]") {
    StyleLexicon lexicon;
    lexicon.conjunctions = {U"что", U"но"};
    const auto r = features_of({U"что? но да"}, kGroupPunctuation, lexicon);
    REQUIRE_THAT(value(r, U"p:comma_before_conj"), WithinAbs(0.0, 1e-12));
}

TEST_CASE("style: no_space_after_comma", "[habits]") {
    const auto r1 = features_of({U"привет,как дела, друг"}, kGroupPunctuation);
    REQUIRE_THAT(value(r1, U"p:no_space_after_comma"), WithinAbs(0.5, 1e-12));
    
    const auto r2 = features_of({U"1,5 кг"}, kGroupPunctuation);
    REQUIRE_THAT(value(r2, U"p:no_space_after_comma"), WithinAbs(0.0, 1e-12));
}

TEST_CASE("style: space_before_punct", "[habits]") {
    const auto r = features_of({U"да , нет . ну!"}, kGroupPunctuation);
    REQUIRE_THAT(value(r, U"p:space_before_punct"), WithinAbs(2.0 / 3, 1e-12));
}

TEST_CASE("style: dash", "[habits]") {
    const auto r = features_of({U"я - дома", U"я — тут", U"а–б", U"ко-ко"}, kGroupPunctuation);
    REQUIRE_THAT(value(r, U"p:dash"), WithinAbs(0.75, 1e-12));
}

TEST_CASE("style: guillemets", "[habits]") {
    const auto r1 = features_of({U"«да» и \"нет\""}, kGroupPunctuation);
    REQUIRE_THAT(value(r1, U"p:guillemets"), WithinAbs(0.5, 1e-12));
    
    const auto r2 = features_of({U"без кавычек"}, kGroupPunctuation);
    REQUIRE_THAT(value(r2, U"p:guillemets"), WithinAbs(0.0, 1e-12));
}

TEST_CASE("style: end_none", "[habits]") {
    const auto r = features_of({U"привет", U"привет.", U"привет))", U"ок1", U"ок:)"}, kGroupPunctuation);
    REQUIRE_THAT(value(r, U"p:end_none"), WithinAbs(0.4, 1e-12));
}

TEST_CASE("style: punctuation group disabled", "[habits]") {
    const auto r = features_of({U"привет, мир"}, kGroupOrthography);
    REQUIRE(r.count(U"p:comma_per_word") == 0);
    REQUIRE(r.count(U"p:end_none") == 0);
}

TEST_CASE("style: caps_words", "[habits]") {
    const auto r = features_of({U"ЭТО ОК", U"я в ОК", U"А Б", U"тихо"}, kGroupOrthography);
    REQUIRE_THAT(value(r, U"f:caps_words"), WithinAbs(0.75, 1e-12));
}

TEST_CASE("style: capital_after_dot", "[habits]") {
    const auto r = features_of({U"Привет. Как дела? да. Ок! нет"}, kGroupOrthography);
    REQUIRE_THAT(value(r, U"f:capital_after_dot"), WithinAbs(0.5, 1e-12));
}

TEST_CASE("style: repeat_letters", "[habits]") {
    const auto r1 = features_of({U"приветтт", U"даааа нет", U"ок", U"ааа ббб", U"тест"}, kGroupOrthography);
    REQUIRE_THAT(value(r1, U"o:repeat_letters"), WithinAbs(0.8, 1e-12));
    
    const auto r2 = features_of({U"ну))))", U"ну!!!"}, kGroupOrthography);
    REQUIRE_THAT(value(r2, U"o:repeat_letters"), WithinAbs(0.0, 1e-12));
    
    const auto r3 = features_of({U"ААа"}, kGroupOrthography);
    REQUIRE_THAT(value(r3, U"o:repeat_letters"), WithinAbs(1.0, 1e-12));
}

TEST_CASE("style: tsya_share", "[habits]") {
    const auto r1 = features_of({U"он смеётся, надо смеяться, они учатся, хочу учиться"}, kGroupOrthography);
    REQUIRE_THAT(value(r1, U"o:tsya_share"), WithinAbs(0.5, 1e-12));
    
    const auto r2 = features_of({U"привет"}, kGroupOrthography);
    REQUIRE_THAT(value(r2, U"o:tsya_share"), WithinAbs(0.0, 1e-12));
}

TEST_CASE("style: mixed_script", "[habits]") {
    const auto r = features_of({U"привeт мир hello"}, kGroupOrthography);
    REQUIRE_THAT(value(r, U"o:mixed_script"), WithinAbs(1.0 / 3, 1e-12));
}

TEST_CASE("style: double_space", "[habits]") {
    const auto r = features_of({U"да  нет", U"да   нет  ок", U"да нет", U"ок"}, kGroupOrthography);
    REQUIRE_THAT(value(r, U"o:double_space"), WithinAbs(0.75, 1e-12));
}

TEST_CASE("style: nonstandard words", "[habits]") {
    StyleLexicon lexicon;
    lexicon.nonstandard_words = {U"щас", U"ваще"};
    const auto r = features_of({U"щас приду ваще", U"Щас"}, kGroupOrthography, lexicon);
    REQUIRE_THAT(value(r, U"o:nonstandard"), WithinAbs(0.75, 1e-12));
    REQUIRE_THAT(value(r, U"ms:щас"), WithinAbs(0.5, 1e-12));
    REQUIRE_THAT(value(r, U"ms:ваще"), WithinAbs(0.25, 1e-12));
}

TEST_CASE("style: nonstandard words zero frequency", "[habits]") {
    StyleLexicon lexicon;
    lexicon.nonstandard_words = {U"щас", U"ваще"};
    const auto r = features_of({U"привет"}, kGroupOrthography, lexicon);
    REQUIRE(r.count(U"ms:щас") == 1);
    REQUIRE(value(r, U"ms:щас") == 0.0);
}

TEST_CASE("style: avg_word_len", "[habits]") {
    const auto r = features_of({U"я иду домой самостоятельно"}, kGroupWords);
    REQUIRE_THAT(value(r, U"w:avg_word_len"), WithinAbs(5.75, 1e-12));
    REQUIRE_THAT(value(r, U"w:long_words"), WithinAbs(0.25, 1e-12));
    REQUIRE_THAT(value(r, U"w:short_words"), WithinAbs(0.25, 1e-12));
}

TEST_CASE("style: avg_word_len with hyphen", "[habits]") {
    const auto r = features_of({U"что-то"}, kGroupWords);
    REQUIRE_THAT(value(r, U"w:avg_word_len"), WithinAbs(5.0, 1e-12));
}

TEST_CASE("style: mattr short text", "[habits]") {
    const auto r1 = features_of({U"да да нет нет"}, kGroupWords);
    REQUIRE_THAT(value(r1, U"w:mattr"), WithinAbs(0.5, 1e-12));
    
    const auto r2 = features_of({U"раз два три"}, kGroupWords);
    REQUIRE_THAT(value(r2, U"w:mattr"), WithinAbs(1.0, 1e-12));
    
    const auto r3 = features_of({}, kGroupWords);
    REQUIRE_THAT(value(r3, U"w:mattr"), WithinAbs(0.0, 1e-12));
}

TEST_CASE("style: mattr long text", "[habits]") {
    std::vector<std::u32string> messages;
    std::u32string same_word;
    for (int i = 0; i < 60; ++i) {
        same_word += U"да ";  // 60 одинаковых слов: в каждом окне из 50 слов одно различное
    }
    messages.push_back(same_word);
    const auto r1 = features_of(messages, kGroupWords);
    REQUIRE_THAT(value(r1, U"w:mattr"), WithinAbs(0.02, 1e-12));
    
    std::u32string distinct;
    for (int i = 0; i < 60; ++i) {  // 60 различных слов в одном сообщении
        distinct += U"сл";
        distinct.push_back(static_cast<char32_t>(0x0430 + i % 32));
        distinct.push_back(static_cast<char32_t>(0x0430 + i / 32));
        distinct.push_back(U' ');
    }
    messages.assign(1, distinct);
    const auto r2 = features_of(messages, kGroupWords);
    REQUIRE_THAT(value(r2, U"w:mattr"), WithinAbs(1.0, 1e-12));
}

TEST_CASE("style: avg_sentence_words", "[habits]") {
    const auto r = features_of({U"Привет. Как дела? Нормально"}, kGroupSentences);
    REQUIRE_THAT(value(r, U"s:avg_sentence_words"), WithinAbs(4.0 / 3, 1e-12));
    REQUIRE_THAT(value(r, U"s:per_message"), WithinAbs(3.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:short_share"), WithinAbs(1.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:long_share"), WithinAbs(0.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:multi_share"), WithinAbs(1.0, 1e-12));
}

TEST_CASE("style: long sentences", "[habits]") {
    const auto r = features_of({U"а б в г д е ж з и к л м н о п"}, kGroupSentences);
    REQUIRE_THAT(value(r, U"s:avg_sentence_words"), WithinAbs(15.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:long_share"), WithinAbs(1.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:short_share"), WithinAbs(0.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:per_message"), WithinAbs(1.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:multi_share"), WithinAbs(0.0, 1e-12));
}

TEST_CASE("style: newline as sentence boundary", "[habits]") {
    const auto r = features_of({U"раз два\nтри"}, kGroupSentences);
    REQUIRE_THAT(value(r, U"s:per_message"), WithinAbs(2.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:avg_sentence_words"), WithinAbs(1.5, 1e-12));
    REQUIRE_THAT(value(r, U"s:multi_share"), WithinAbs(1.0, 1e-12));
}

TEST_CASE("style: ellipsis as sentence boundary", "[habits]") {
    const auto r = features_of({U"ну… да"}, kGroupSentences);
    REQUIRE_THAT(value(r, U"s:per_message"), WithinAbs(2.0, 1e-12));
}

TEST_CASE("style: no words no sentences", "[habits]") {
    const auto r = features_of({U"))))", U"123"}, kGroupSentences);
    REQUIRE_THAT(value(r, U"s:per_message"), WithinAbs(0.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:avg_sentence_words"), WithinAbs(0.0, 1e-12));
    REQUIRE_THAT(value(r, U"s:short_share"), WithinAbs(0.0, 1e-12));
}

TEST_CASE("style: key count for different groups", "[habits]") {
    StyleLexicon lexicon;
    lexicon.function_words = {U"и"};
    lexicon.filler_words = {U"ну"};
    lexicon.nonstandard_words = {U"щас"};
    
    const auto r1 = features_of({}, kGroupAll, lexicon);
    REQUIRE(r1.size() == 41);
    for (const auto& entry : r1) {
        REQUIRE(entry.second == 0.0);
    }
    
    const auto r2 = features_of({U"   ", U""}, 0, lexicon);
    REQUIRE(r2.size() == 17);
    for (const auto& entry : r2) {
        REQUIRE(entry.second == 0.0);
    }
    
    const auto r3 = features_of({}, kGroupPunctuation, lexicon);
    REQUIRE(r3.size() == 24);
    
    const auto r4 = features_of({}, kGroupOrthography, lexicon);
    REQUIRE(r4.size() == 25);
    
    const auto r5 = features_of({}, kGroupWords, lexicon);
    REQUIRE(r5.size() == 21);
    
    const auto r6 = features_of({}, kGroupSentences, lexicon);
    REQUIRE(r6.size() == 22);
}

TEST_CASE("style: stability with large input", "[habits]") {
    std::vector<std::u32string> messages;
    std::u32string repeated = U"да нет ну ";
    for (int i = 0; i < 20000; ++i) {
        messages.push_back(repeated);
    }
    const auto r = features_of(messages, kGroupAll);
    for (const auto& entry : r) {
        REQUIRE(std::isfinite(entry.second));
    }
    REQUIRE(value(r, U"w:mattr") > 0.0);
    REQUIRE(value(r, U"w:mattr") <= 1.0);
}

TEST_CASE("style: ignored tokens", "[habits]") {
    StyleLexicon lexicon;
    lexicon.ignored_tokens = {U"<URL>"};
    const auto r = features_of({U"<URL> привет, мир <URL>"}, kGroupPunctuation, lexicon);
    REQUIRE_THAT(value(r, U"p:comma_per_word"), WithinAbs(0.5, 1e-12));
    REQUIRE_THAT(value(r, U"p:end_none"), WithinAbs(1.0, 1e-12));
}
