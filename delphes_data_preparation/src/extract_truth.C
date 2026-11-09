// Project-owned truth export. Read split numeric ROOT leaves; no Delphes library needed.
#include <TFile.h>
#include <TTree.h>
#include <TLeaf.h>
#include <TSystem.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace truth_export {
TLeaf *require_leaf(TTree *tree, const std::string &name) {
  auto *leaf = tree->GetLeaf(name.c_str());
  if (!leaf) throw std::runtime_error("Missing leaf: " + name);
  tree->SetBranchStatus(name.c_str(), 1);
  return leaf;
}

char channel(const std::vector<int> &pid, const std::vector<int> &m1,
             const std::vector<int> &m2, const std::vector<int> &d1,
             const std::vector<int> &d2, bool background) {
  int terminals = 0;
  char label = 0;
  for (int z=0; z<int(pid.size()); ++z) {
    if (pid[z] != 23) continue;
    if (background) throw std::runtime_error("Unexpected Z in background source");
    if (d1[z] < 0 || d2[z] < d1[z] || d2[z] >= int(pid.size()))
      throw std::runtime_error("Invalid Z daughter range");
    bool has_z_copy = false;
    std::vector<int> fermions;
    for (int child=d1[z]; child<=d2[z]; ++child) {
      if (m1[child] != z && m2[child] != z)
        throw std::runtime_error("Z daughter/mother links disagree");
      if (pid[child] == 23) has_z_copy = true;
      else if (pid[child] != 22) fermions.push_back(pid[child]);
    }
    if (has_z_copy) continue; // Follow resonance copies, not secondary tau decays.
    if (fermions.size() != 2 || fermions[0] != -fermions[1])
      throw std::runtime_error("Z does not have one unambiguous fermion pair");
    int flavour = std::abs(fermions[0]);
    if (flavour >= 1 && flavour <= 5) label = 'h';
    else if (flavour == 11) label = 'e';
    else if (flavour == 13) label = 'm';
    else if (flavour == 15) label = 't';
    else throw std::runtime_error("Unexpected Z decay flavour");
    ++terminals;
  }
  if (background) return 'n';
  if (terminals != 1) throw std::runtime_error("Expected exactly one terminal Z decay");
  return label;
}
}

void extract_truth(const char *root_path, const char *features_path,
                   const char *output_path, bool background=false) {
  const std::string temporary = std::string(output_path) + ".partial";
  Long64_t event = -1;
  try {
    if (!gSystem->AccessPathName(output_path) || !gSystem->AccessPathName(temporary.c_str()))
      throw std::runtime_error("Output already exists");
    TFile source(root_path, "READ");
    auto *tree = source.Get<TTree>("Delphes");
    if (source.IsZombie() || !tree) throw std::runtime_error("Missing Delphes tree");
    tree->SetBranchStatus("*", 0);
    std::map<std::string,TLeaf*> leaves;
    for (const auto *name : {"Particle.PID", "Particle.M1", "Particle.M2", "Particle.D1", "Particle.D2",
                            "Electron_size", "Muon_size", "Jet_size", "EFlowTrack.PT", "EFlowTrack.Eta",
                            "EFlowTrack.Mass", "EFlowPhoton.E", "EFlowNeutralHadron.E"})
      leaves[name] = truth_export::require_leaf(tree, name);
    std::ifstream features(features_path);
    if (!features) throw std::runtime_error("Cannot open reconstructed features");
    std::ofstream output(temporary);
    if (!output) throw std::runtime_error("Cannot create truth output");
    output << "nEvt,true_channel\n";
    std::map<char,Long64_t> counts;
    double maximum_energy_difference = 0;
    for (event=0; event<tree->GetEntries(); ++event) {
      if (tree->GetEntry(event) <= 0) throw std::runtime_error("Cannot read ROOT entry");
      std::string line;
      if (!std::getline(features, line)) throw std::runtime_error("Missing feature row");
      std::istringstream row(line);
      std::vector<double> fields;
      double value;
      while (row >> value) fields.push_back(value);
      if (!row.eof() || fields.size() != 27 ||
          !std::all_of(fields.begin(), fields.end(), [](double x){return std::isfinite(x);}) ||
          fields[0] != double(event))
        throw std::runtime_error("Invalid feature row or nonmatching ROOT-entry ID");
      if (fields[6] != leaves["Electron_size"]->GetValue() ||
          fields[7] != leaves["Muon_size"]->GetValue() ||
          fields[8] != leaves["Jet_size"]->GetValue())
        throw std::runtime_error("ROOT/feature multiplicities differ");
      double energy = 0;
      int tracks = leaves["EFlowTrack.PT"]->GetLen();
      if (leaves["EFlowTrack.Eta"]->GetLen() != tracks || leaves["EFlowTrack.Mass"]->GetLen() != tracks)
        throw std::runtime_error("Inconsistent track leaves");
      for (int i=0; i<tracks; ++i) {
        double momentum = leaves["EFlowTrack.PT"]->GetValue(i) * std::cosh(leaves["EFlowTrack.Eta"]->GetValue(i));
        double mass = leaves["EFlowTrack.Mass"]->GetValue(i);
        energy += std::sqrt(momentum*momentum + mass*mass);
      }
      for (const auto *name : {"EFlowPhoton.E", "EFlowNeutralHadron.E"})
        for (int i=0; i<leaves[name]->GetLen(); ++i) energy += leaves[name]->GetValue(i);
      double difference = std::abs(energy - fields[4]);
      maximum_energy_difference = std::max(maximum_energy_difference, difference);
      if (!std::isfinite(energy) || difference > 1e-5)
        throw std::runtime_error("ROOT/feature total energy differs");
      std::vector<std::vector<int>> record;
      int particles = leaves["Particle.PID"]->GetLen();
      for (const auto *name : {"Particle.PID", "Particle.M1", "Particle.M2", "Particle.D1", "Particle.D2"}) {
        if (leaves[name]->GetLen() != particles) throw std::runtime_error("Inconsistent particle leaves");
        std::vector<int> values;
        for (int i=0; i<particles; ++i) values.push_back(int(leaves[name]->GetValue(i)));
        record.push_back(values);
      }
      char label = truth_export::channel(record[0], record[1], record[2], record[3], record[4], background);
      output << event << ',' << label << '\n';
      ++counts[label];
    }
    std::string extra;
    if (std::getline(features, extra)) throw std::runtime_error("Feature file contains extra rows");
    output.close();
    if (!output || std::rename(temporary.c_str(), output_path) != 0)
      throw std::runtime_error("Cannot finalize truth output");
    std::cout << "Validated ROOT/feature alignment for " << event << " events; max energy difference "
              << maximum_energy_difference << " GeV\n";
    for (const auto &item : counts) std::cout << item.first << ": " << item.second << '\n';
  } catch (const std::exception &error) {
    std::cerr << "Truth extraction failed at event " << event << ": " << error.what() << '\n';
    gSystem->Exit(1);
  }
}
