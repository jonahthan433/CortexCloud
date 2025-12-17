import { Bot, Phone, MessageSquare, Calendar, BarChart3, Workflow, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Link } from 'react-router-dom';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import PageTransition from '@/components/PageTransition';
import FadeIn from '@/components/FadeIn';

const Services = () => {
  const services = [
    {
      icon: Bot,
      title: 'AI Customer Support',
      description: 'Deploy intelligent chatbots that handle customer inquiries 24/7 with human-like understanding and empathy.',
      features: ['Multi-language support', 'Sentiment detection', 'Seamless handoff to humans', 'Custom knowledge base'],
    },
    {
      icon: Phone,
      title: 'Voice AI Agents',
      description: 'Natural-sounding voice agents that can handle calls, schedule appointments, and provide information.',
      features: ['Natural speech synthesis', 'Real-time transcription', 'Call routing', 'CRM integration'],
    },
    {
      icon: MessageSquare,
      title: 'WhatsApp Automation',
      description: 'Engage customers on their favorite messaging platform with automated yet personalized conversations.',
      features: ['Rich media support', 'Quick replies', 'Product catalogs', 'Payment integration'],
    },
    {
      icon: Calendar,
      title: 'Smart Scheduling',
      description: 'AI-powered scheduling that finds the perfect meeting times and handles all the back-and-forth.',
      features: ['Calendar sync', 'Time zone handling', 'Automatic rescheduling', 'Buffer time management'],
    },
    {
      icon: BarChart3,
      title: 'Conversation Intelligence',
      description: 'Turn every conversation into actionable insights with advanced analytics and reporting.',
      features: ['Sentiment analysis', 'Topic extraction', 'Performance metrics', 'Trend identification'],
    },
    {
      icon: Workflow,
      title: 'Custom Automation',
      description: 'Build custom workflows that connect your AI agents with your existing tools and processes.',
      features: ['API integrations', 'Custom triggers', 'Conditional logic', 'Data transformation'],
    },
  ];

  const process = [
    {
      step: '01',
      title: 'Discovery',
      description: 'We analyze your workflows, identify automation opportunities, and understand your specific needs.',
    },
    {
      step: '02',
      title: 'Design',
      description: 'Our team designs custom AI solutions tailored to your business processes and goals.',
    },
    {
      step: '03',
      title: 'Deploy',
      description: 'We deploy and configure your AI agents, integrating them seamlessly with your existing systems.',
    },
    {
      step: '04',
      title: 'Optimize',
      description: 'Continuous monitoring and improvement to ensure your AI agents perform at their best.',
    },
  ];

  return (
    <PageTransition>
      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="pt-24 md:pt-32">
          {/* Hero Section */}
          <section className="py-16 md:py-24 relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-hero" />
            <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl animate-pulse-glow" />
            
            <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
              <FadeIn>
                <div className="max-w-3xl mx-auto text-center space-y-6">
                  <span className="inline-block glass px-4 py-2 rounded-full text-sm font-medium text-primary">
                    Our Services
                  </span>
                  <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold font-display">
                    AI Solutions for <span className="text-gradient">Every Need</span>
                  </h1>
                  <p className="text-lg text-muted-foreground">
                    From customer support to lead generation, we provide comprehensive AI automation services that transform how you do business.
                  </p>
                </div>
              </FadeIn>
            </div>
          </section>

          {/* Services Grid */}
          <section className="py-16 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                {services.map((service, index) => (
                  <FadeIn key={index} delay={index * 0.1}>
                    <div className="group relative h-full">
                      <div className="absolute -inset-1 bg-gradient-primary rounded-2xl opacity-0 group-hover:opacity-20 blur-xl transition-opacity duration-500" />
                      <div className="relative glass-strong rounded-2xl p-8 h-full transition-transform duration-300 hover:-translate-y-2">
                        <div className="w-14 h-14 rounded-xl bg-gradient-primary flex items-center justify-center mb-6">
                          <service.icon size={28} className="text-primary-foreground" />
                        </div>
                        <h3 className="text-xl font-bold font-display mb-3">{service.title}</h3>
                        <p className="text-muted-foreground mb-6">{service.description}</p>
                        <ul className="space-y-2">
                          {service.features.map((feature, fIndex) => (
                            <li key={fIndex} className="flex items-center gap-2 text-sm">
                              <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                              <span className="text-muted-foreground">{feature}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </section>

          {/* Process Section */}
          <section className="py-16 md:py-24 relative bg-secondary/20">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="text-center mb-12">
                  <h2 className="text-3xl sm:text-4xl font-bold font-display">
                    Our <span className="text-gradient">Process</span>
                  </h2>
                  <p className="text-muted-foreground mt-4 max-w-2xl mx-auto">
                    A proven methodology that ensures successful AI implementation every time.
                  </p>
                </div>
              </FadeIn>
              
              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-8">
                {process.map((item, index) => (
                  <FadeIn key={index} delay={index * 0.15}>
                    <div className="relative">
                      {index < process.length - 1 && (
                        <div className="hidden lg:block absolute top-8 left-full w-full h-0.5 bg-gradient-to-r from-primary/50 to-transparent" />
                      )}
                      <div className="glass-strong rounded-2xl p-6 text-center">
                        <div className="w-16 h-16 rounded-full bg-gradient-primary flex items-center justify-center mx-auto mb-4">
                          <span className="text-2xl font-bold text-primary-foreground">{item.step}</span>
                        </div>
                        <h3 className="text-lg font-bold font-display mb-2">{item.title}</h3>
                        <p className="text-sm text-muted-foreground">{item.description}</p>
                      </div>
                    </div>
                  </FadeIn>
                ))}
              </div>
            </div>
          </section>

          {/* CTA Section */}
          <section className="py-16 md:py-24 relative">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <FadeIn>
                <div className="relative">
                  <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 rounded-3xl blur-3xl" />
                  <div className="relative glass-strong rounded-3xl p-8 md:p-16 text-center">
                    <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold font-display mb-4">
                      Ready to Transform Your Business?
                    </h2>
                    <p className="text-muted-foreground mb-8 max-w-2xl mx-auto">
                      Let's discuss how CortexCloud can automate your workflows and supercharge your customer experience.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                      <Button variant="primary" size="lg" asChild>
                        <Link to="/contact">
                          Get Started <ArrowRight size={18} className="ml-2" />
                        </Link>
                      </Button>
                      <Button variant="outline" size="lg" asChild>
                        <Link to="/pricing">
                          View Pricing
                        </Link>
                      </Button>
                    </div>
                  </div>
                </div>
              </FadeIn>
            </div>
          </section>
        </main>

        <Footer />
      </div>
    </PageTransition>
  );
};

export default Services;
