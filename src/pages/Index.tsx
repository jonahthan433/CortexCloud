import Navbar from '@/components/Navbar';
import HeroSection from '@/components/HeroSection';
import TrustBadges from '@/components/TrustBadges';
import FeaturesSection from '@/components/FeaturesSection';
import HowItWorksSection from '@/components/HowItWorksSection';
import CustomSolutionsSection from '@/components/CustomSolutionsSection';
import CaseStudiesSection from '@/components/CaseStudiesSection';
import FAQSection from '@/components/FAQSection';
import CTASection from '@/components/CTASection';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';

const Index = () => {
  return (
    <PageTransition>
      <div className="min-h-screen bg-background overflow-x-hidden">
        <Navbar />
        <main>
          <HeroSection />
          <TrustBadges />
          <FeaturesSection />
          <HowItWorksSection />
          <CustomSolutionsSection />
          <CaseStudiesSection />
          <FAQSection />
          <CTASection />
        </main>
        <Footer />
      </div>
    </PageTransition>
  );
};

export default Index;
