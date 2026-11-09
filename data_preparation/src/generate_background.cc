// Independent PYTHIA 8 gamma-gamma background for the DELPHI external input.
// Writes the little-endian Fortran sequential LUJETS records used by WINWRITE
// in the official DELPHI PYTHIA example (two beam entries + final particles).
#include "Pythia8/Pythia.h"

#include <cmath>
#include <climits>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <limits>

namespace {
static_assert(CHAR_BIT == 8 && sizeof(float) == 4 &&
              std::numeric_limits<float>::is_iec559,
              "FADGEN requires 8-bit bytes and IEEE-754 binary32 floats");

int parse_integer(const char *text) {
  std::size_t used = 0;
  const std::string value(text);
  const int number = std::stoi(value, &used);
  if (used != value.size()) throw std::invalid_argument("Invalid integer argument");
  return number;
}

struct Particle {
  std::int32_t k[5];
  float p[5];
  float v[5];
};

void write_int(std::ofstream &out, std::int32_t value) {
  out.write(reinterpret_cast<const char *>(&value), sizeof(value));
}

void write_particle(std::ofstream &out, const Particle &particle) {
  out.write(reinterpret_cast<const char *>(particle.k), sizeof(particle.k));
  out.write(reinterpret_cast<const char *>(particle.p), sizeof(particle.p));
  out.write(reinterpret_cast<const char *>(particle.v), sizeof(particle.v));
}

Particle beam(std::int32_t id, float pz) {
  return {{21, id, 0, 0, 0}, {0.0f, 0.0f, pz, 45.625f, 0.000511f}, {}};
}

Particle final_particle(const Pythia8::Particle &source) {
  return {{1, static_cast<std::int32_t>(source.id()), 0, 0, 0},
          {static_cast<float>(source.px()), static_cast<float>(source.py()),
           static_cast<float>(source.pz()), static_cast<float>(source.e()),
           static_cast<float>(source.m())},
          {}};
}

void write_event(std::ofstream &out, const std::vector<Particle> &particles) {
  const auto count = static_cast<std::int32_t>(particles.size());
  const auto bytes = static_cast<std::int32_t>(sizeof(count) +
                                                count * (5 + 5 + 5) * sizeof(std::int32_t));
  write_int(out, bytes);
  write_int(out, count);
  for (const auto &particle : particles) write_particle(out, particle);
  write_int(out, bytes);
  if (!out) throw std::runtime_error("Cannot write a complete FADGEN record");
}
} // namespace

int main(int argc, char **argv) {
  if (argc != 4) {
    std::cerr << "Usage: generate_background OUTPUT.fadgen EVENTS SEED\n";
    return 2;
  }
  try {
    const std::string output = argv[1];
    const int requested = parse_integer(argv[2]);
    const int seed = parse_integer(argv[3]);
    if (requested < 1 || seed < 1 || seed > 900000000)
      throw std::invalid_argument("Invalid event count or seed");
    const std::uint16_t byte_order = 1;
    if (*reinterpret_cast<const unsigned char *>(&byte_order) != 1)
      throw std::runtime_error("This FADGEN writer requires a little-endian machine");
    Pythia8::Pythia generator;
    const auto setting = [&](const std::string &value) {
      if (!generator.readString(value))
        throw std::runtime_error("PYTHIA rejected setting: " + value);
    };
    setting("Beams:idA = 11");
    setting("Beams:idB = -11");
    setting("Beams:eCM = 91.25");
    setting("PDF:lepton2gamma = on");
    setting("Photon:ProcessType = 4");
    setting("Photon:Wmin = 10.0");
    setting("PhotonCollision:all = on");
    setting("Random:setSeed = on");
    setting("Random:seed = " + std::to_string(seed));
    setting("Main:timesAllowErrors = 5");
    if (!generator.init()) throw std::runtime_error("PYTHIA initialization failed");

    if (std::ifstream(output).good())
      throw std::runtime_error("Refusing to overwrite output file");
    std::ofstream out(output, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("Cannot open output file");
    int written = 0;
    std::int64_t attempts = 0;
    while (written < requested && attempts < std::int64_t(requested) * 20) {
      ++attempts;
      if (!generator.next()) continue;
      std::vector<Particle> particles;
      particles.push_back(beam(11, 45.625f));
      particles.push_back(beam(-11, -45.625f));
      double final_energy = 0.0;
      for (int index = 0; index < generator.event.size(); ++index) {
        const auto &source = generator.event[index];
        if (!source.isFinal()) continue;
        if (particles.size() >= 3999) throw std::runtime_error("LUJETS particle limit exceeded");
        particles.push_back(final_particle(source));
        final_energy += source.e();
      }
      if (particles.size() <= 2 || !std::isfinite(final_energy) ||
          std::abs(final_energy - 91.25) > 0.1)
        throw std::runtime_error("Invalid final-state energy conservation");
      write_event(out, particles);
      ++written;
    }
    if (written != requested) throw std::runtime_error("Too few generated events");
    out.close();
    if (!out) throw std::runtime_error("Failed to flush/close the FADGEN output");
    std::cout << "events=" << written << " attempts=" << attempts
              << " seed=" << seed << " output=" << output << '\n';
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
