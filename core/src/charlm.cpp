// charlm.cpp
// Реализация модели символов CharModel.
// Внутри namespace chatstyle объявлен анонимный namespace, где находится
// реализация класса и вспомогательные структуры.
// Комментарии написаны на русском языке.

#include "chatstyle/charlm.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace chatstyle {

namespace {

// Статистика для одного контекста.
struct ContextStats {
    std::size_t total = 0;                                   // общее число наблюдений
    std::unordered_map<char32_t, std::size_t> next;          // количество появлений каждого следующего символа
};

// Класс модели символов.
class CharModel {
public:
    // Конструктор.
    // order      – порядок модели (≥1).
    // vocab_size – размер алфавита, используется для базовой вероятности 1/vocab_size.
    CharModel(std::size_t order, std::size_t vocab_size)
        : order_(order)
        , vocab_size_(vocab_size)
        , base_prob_(vocab_size_ ? 1.0 / static_cast<double>(vocab_size_) : 0.0) {
        // order должно быть ≥ 1, проверка в отладочных сборках.
        assert(order_ >= 1);
    }

    // Обучение модели на наборе сообщений.
    // Каждое сообщение преобразуется в последовательность:
    //   (order-1) символов U'\x02', затем символы сообщения, затем U'\n'.
    // Для каждой позиции i (от order-1 до конца) и каждой длины контекста k
    // (от 0 до order-1) обновляются счётчики.
    void train(const std::vector<std::u32string>& messages) {
        for (const auto& msg : messages) {
            // Формируем дополненную строку.
            std::u32string augmented(order_ - 1, U'\x02');
            augmented += msg;
            augmented += U'\n';

            const std::size_t len = augmented.size();
            // i – позиция текущего символа (включая добавленный \n).
            for (std::size_t i = order_ - 1; i < len; ++i) {
                const char32_t cur = augmented[i];
                // Для всех контекстов длиной k.
                for (std::size_t k = 0; k <= order_ - 1; ++k) {
                    const std::size_t start = i - k;
                    const std::u32string context = augmented.substr(start, k);
                    ContextStats& stats = stats_[context];
                    ++stats.total;
                    ++stats.next[cur];
                }
            }
        }
    }

    // Вычисление количества бит, затраченных на кодирование набора сообщений.
    // chars – количество оценённых символов (включая символы \n).
    // Возвращает суммарное количество бит (не среднее).
    double bits(const std::vector<std::u32string>& messages, std::size_t& chars) const {
        double total_bits = 0.0;
        std::size_t total_chars = 0;

        for (const auto& msg : messages) {
            std::u32string augmented(order_ - 1, U'\x02');
            augmented += msg;
            augmented += U'\n';

            const std::size_t len = augmented.size();
            for (std::size_t i = order_ - 1; i < len; ++i) {
                const char32_t cur = augmented[i];
                // История до текущего символа включительно.
                const std::u32string history = augmented.substr(0, i + 1);
                const double p = prob(history, order_ - 1, cur);
                total_bits += -std::log2(p);
                ++total_chars;
            }
        }

        chars = total_chars;
        return total_bits;
    }

private:
    // Рекурсивное вычисление вероятности P(c | контекст) по методу Witten‑Bell.
    // history – строка, содержащая все символы до текущего включительно.
    // k       – длина контекста (от 0 до order_-1).
    // c       – текущий символ.
    double prob(const std::u32string& history, std::size_t k, char32_t c) const {
        // Базовый уровень (k == 0) использует базовую вероятность.
        double p_lower = base_prob_;

        // Если k > 0, рекурсивно получаем нижнюю вероятность.
        if (k > 0) {
            p_lower = prob(history, k - 1, c);
        }

        // Выделяем контекст длиной k (символы перед текущим).
        const std::size_t ctx_start = history.size() - k - 1;
        const std::u32string context = history.substr(ctx_start, k);

        // Ищем статистику для данного контекста.
        auto it = stats_.find(context);
        if (it == stats_.end() || it->second.total == 0) {
            // Нет статистики – возвращаем нижнюю вероятность.
            return p_lower;
        }

        const ContextStats& cs = it->second;
        const std::size_t count_c = cs.next.count(c) ? cs.next.at(c) : 0;
        const std::size_t T = cs.next.size();          // число различных символов после контекста
        const std::size_t total = cs.total;

        // Формула Виттен‑Белла.
        return (static_cast<double>(count_c) + static_cast<double>(T) * p_lower) /
               (static_cast<double>(total) + static_cast<double>(T));
    }

    std::size_t order_;                         // порядок модели
    std::size_t vocab_size_;                    // размер алфавита
    double base_prob_;                          // 1 / vocab_size
    std::unordered_map<std::u32string, ContextStats> stats_; // статистика по контекстам
};

// Сумма (длина сообщения + 1) по всем сообщениям.
std::size_t chars_of(const std::vector<std::u32string>& messages) {
    std::size_t total = 0;
    for (const auto& msg : messages) {
        total += msg.size() + 1;
    }
    return total;
}

// Возвращает префикс сообщений, не превышающий budget символов (длина+1).
// Если budget == 0, возвращает копию всех сообщений.
// Минимум одно сообщение, если сообщения есть.
std::vector<std::u32string> prefix(const std::vector<std::u32string>& messages, std::size_t budget) {
    if (budget == 0) {
        return messages;
    }
    std::vector<std::u32string> result;
    std::size_t current = 0;
    for (const auto& msg : messages) {
        if (result.empty()) {
            result.push_back(msg);
            current += msg.size() + 1;
        } else if (current + msg.size() + 1 <= budget) {
            result.push_back(msg);
            current += msg.size() + 1;
        } else {
            break;
        }
    }
    return result;
}

} // namespace

std::vector<CharLmResult> charlm_compare(
    const std::vector<std::u32string>& unknown,
    const std::vector<std::vector<std::u32string>>& candidates,
    const CharLmOptions& options) {
    // Порядок должен быть положительным.
    if (options.order == 0) {
        throw std::invalid_argument("order must be positive");
    }

    // Результаты по умолчанию.
    std::vector<CharLmResult> results(candidates.size());

    // Если неизвестный пустой или кандидатов меньше двух — ничего не делаем.
    if (chars_of(unknown) == 0 || candidates.size() < 2) {
        return results;
    }

    // Алфавит: все символы из неизвестного и кандидатов + \n и \x02.
    std::set<char32_t> alphabet;
    for (const auto& msg : unknown) {
        for (char32_t c : msg) {
            alphabet.insert(c);
        }
    }
    for (const auto& cand : candidates) {
        for (const auto& msg : cand) {
            for (char32_t c : msg) {
                alphabet.insert(c);
            }
        }
    }
    alphabet.insert(U'\n');
    alphabet.insert(U'\x02');
    // vocab_size = размер алфавита + 1 (один «невиданный» символ).
    const std::size_t vocab_size = alphabet.size() + 1;

    // Находим «непустые» кандидаты (chars_of > 0).
    std::vector<std::size_t> active;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (chars_of(candidates[i]) > 0) {
            active.push_back(i);
        }
    }

    // Если непустых кандидатов меньше двух — возвращаем результаты.
    if (active.size() < 2) {
        return results;
    }

    // Вычисляем L: минимум chars_of по непустым кандидатам (если balance), иначе 0.
    std::size_t L = 0;
    if (options.balance) {
        L = chars_of(candidates[active[0]]);
        for (std::size_t idx : active) {
            L = std::min(L, chars_of(candidates[idx]));
        }
    }

    const std::size_t n = active.size();
    // budget_rest = ceil(L / (n - 1)), либо 0 если L == 0.
    const std::size_t budget_rest = (L == 0) ? 0 : (L + n - 2) / (n - 1);

    for (std::size_t i : active) {
        // Модель кандидата.
        CharModel cand_model(options.order, vocab_size);
        cand_model.train(prefix(candidates[i], L));

        // Модель остальных.
        CharModel rest_model(options.order, vocab_size);
        for (std::size_t j : active) {
            if (j != i) {
                rest_model.train(prefix(candidates[j], budget_rest));
            }
        }

        std::size_t chars = 0;
        std::size_t chars_r = 0;
        double bits_c = cand_model.bits(unknown, chars);
        double bits_r = rest_model.bits(unknown, chars_r);

        results[i].available = true;
        results[i].bits_candidate = bits_c / static_cast<double>(chars);
        results[i].bits_rest = bits_r / static_cast<double>(chars_r);
        results[i].llr = results[i].bits_rest - results[i].bits_candidate;
        results[i].chars_scored = chars;
    }

    return results;
}

} // namespace chatstyle
