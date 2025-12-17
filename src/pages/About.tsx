import { Users, Target, Lightbulb, Award } from 'lucide-react';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const About = () => {
  const values = [
    {
      icon: Target,
      title: 'Mission-Driven',
      description: 'We\'re on a mission to democratize AI automation for businesses of all sizes.',
    },
    {
      icon: Lightbulb,
      title: 'Innovation First',
      description: 'Constantly pushing the boundaries of what AI can achieve for your business.',
    },
    {
      icon: Users,
      title: 'Customer Success',
      description: 'Your success is our success. We\'re committed to delivering real results.',
    },
    {
      icon: Award,
      title: 'Excellence',
      description: 'We hold ourselves to the highest standards in everything we build.',
    },
  ];

  const team = [
    { name: 'Alex Chen', role: 'CEO & Founder', initial: 'AC' },
    { name: 'Sarah Miller', role: 'CTO', initial: 'SM' },
    { name: 'James Wilson', role: 'Head of AI', initial: 'JW' },
    { name: 'Emily Davis', role: 'Head of Product', initial: 'ED' },
    { name: 'Michael Brown', role: 'Head of Sales', initial: 'MB' },
    { name: 'Lisa Zhang', role: 'Head of Support', initial: 'LZ' },
  ];

  return (
    <PageTransition>
      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="pt-24 md:pt-32">
          {/* Hero Section */}
          <section className="py-16 md:py-24 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-hero" />
            <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl animate-pulse-glow" />
            
            <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
              <FadeIn>
                <div className="max-w-3xl mx-auto text-center space-y-6">
                  <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary">
                    About Us
                  </span>
                  <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold font-display">
                    Building the Future of <span className="text-gradient">AI Automation</span>
                  </h1>
                  <p className="text-lg text-muted-foreground">
                    CortexCloud was founded with a simple yet powerful vision: to make cutting-edge AI technology accessible to every business, regardless of size or technical expertise.
                  </p>
                </div>
              </FadeIn>
            </div>
          </section>

          {/* Story Section */}
          <section className="py-16 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <div className="grid lg:grid-cols-2 gap-12 items-center">
                <FadeIn direction="left">
                  <div className="space-y-6">
                    <h2 className="text-3xl sm:text-4xl font-bold font-display">
                      Our <span className="text-gradient">Story</span>
                    </h2>
                    <div className="space-y-4 text-muted-foreground">
                      <p>
                        Founded in 2023, CortexCloud emerged from a simple observation: businesses were drowning in repetitive tasks while struggling to provide the responsive, personalized service their customers demanded.
                      </p>
                      <p>
                        Our founders, with backgrounds spanning AI research, enterprise software, and customer success, came together to build something different—AI agents that don't just respond, but truly understand, learn, and act.
                      </p>
                      <p>
                        Today, we serve over 1000+ businesses worldwide, from ambitious startups to established enterprises, all unified by their desire to work smarter, not harder.
                      </p>
                    </div>
                  </div>
                </FadeIn>
                
                <FadeIn direction="right" delay={0.2}>
                  <div className="relative">
                    <div className="absolute -inset-4 bg-gradient-to-r from-primary/20 to-accent/20 rounded-3xl blur-2xl opacity-30" />
                    <div className="relative glass-strong rounded-2xl p-8 space-y-6">
                      <div className="grid grid-cols-2 gap-6">
                        <div className="text-center p-4 glass rounded-xl">
                          <p className="text-4xl font-bold text-gradient">1000+</p>
                          <p className="text-sm text-muted-foreground">Businesses Served</p>
                        </div>
                        <div className="text-center p-4 glass rounded-xl">
                          <p className="text-4xl font-bold text-gradient">50M+</p>
                          <p className="text-sm text-muted-foreground">Conversations Handled</p>
                        </div>
                        <div className="text-center p-4 glass rounded-xl">
                          <p className="text-4xl font-bold text-gradient">99.9%</p>
                          <p className="text-sm text-muted-foreground">Uptime</p>
                        </div>
                        <div className="text-center p-4 glass rounded-xl">
                          <p className="text-4xl font-bold text-gradient">24/7</p>
                          <p className="text-sm text-muted-foreground">AI Availability</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </FadeIn>
              </div>
            </div>
          </section>

          {/* Values Section */}
          <section className="py-16 md:py-24 relative bg-secondary/20">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="text-center mb-12">
                  <h2 className="text-3xl sm:text-4xl font-bold font-display">
                    Our <span className="text-gradient">Values</span>
                  </h2>
                </div>
              </FadeIn>
              
              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {values.map((value, index) => (
                  <FadeIn key={index} delay={index * 0.1}>
                    <div className="group relative h-full">
                      <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-0 group-hover:opacity-20 blur-xl transition-opacity duration-500" />
                      <div className="relative glass-strong rounded-2xl p-6 h-full transition-transform duration-300 hover:-translate-y-2">
                        <div className="w-12 h-12 rounded-xl bg-gradient-primary flex items-center justify-center mb-4">
                          <value.icon size={24} className="text-primary-foreground" />
                        </div>
                        <h3 className="text-lg font-bold font-display mb-2">{value.title}</h3>
                        <p className="text-sm text-muted-foreground">{value.description}</p>
                      </div>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </section>

          {/* Team Section */}
          <section className="py-16 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="text-center mb-12">
                  <h2 className="text-3xl sm:text-4xl font-bold font-display">
                    Meet the <span className="text-gradient">Team</span>
                  </h2>
                  <p className="text-muted-foreground mt-4 max-w-2xl mx-auto">
                    A diverse group of AI researchers, engineers, and business experts united by a passion for innovation.
                  </p>
                </div>
              </FadeIn>
              
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8 max-w-4xl mx-auto">
                {team.map((member, index) => (
                  <FadeIn key={index} delay={index * 0.1}>
                    <div className="glass-strong rounded-2xl p-6 text-center hover:-translate-y-2 transition-transform duration-300">
                      <div className="w-20 h-20 rounded-full bg-gradient-primary flex items-center justify-center mx-auto mb-4">
                        <span className="text-2xl font-bold text-primary-foreground">{member.initial}</span>
                      </div>
                      <h3 className="font-bold font-display text-lg">{member.name}</h3>
                      <p className="text-sm text-muted-foreground">{member.role}</p>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </section>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
};

export default About;
